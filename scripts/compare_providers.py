"""Compara Groq (Qwen) y Claude (Haiku) con las MISMAS facturas.

Uso (dentro del contenedor, que ya tiene las claves):
  docker compose run --rm -v "$PWD/samples:/samples:ro" web python scripts/compare_providers.py /samples

Por cada imagen mide tiempo, tokens reales, costo, campos leídos y avisos de validación.
Si existe <imagen>.expected.json (ej. {"rnc":"131000002","ncf":"B0100000123","fecha":"2026-11-14","total":5000.00})
calcula además el acierto de cada proveedor contra esa verdad.
Las tarifas son orientativas (sitios de terceros): confírmalas en las páginas oficiales.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from invoice_reader.extractor import ExtractionError, extract_invoice  # noqa: E402
from invoice_reader.images import sniff_media_type  # noqa: E402

PRICES = {"groq": (0.80, 4.00), "claude": (0.10, 0.50)}  # USD por millón de tokens (entrada, salida)
KEYS = {"groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def norm(field: str, v):
    if v is None:
        return None
    if field == "total":
        try:
            return round(float(str(v).replace(",", "")), 2)
        except ValueError:
            return None
    if field == "rnc":
        return re.sub(r"\D", "", str(v))
    return re.sub(r"[^A-Z0-9-]", "", str(v).upper())


def read(provider: str, img: bytes, media: str):
    for attempt in range(4):
        try:
            t = time.time()
            d = extract_invoice(img, media, provider=provider)
            return d, time.time() - t, None
        except ExtractionError as e:
            return None, 0, str(e)
        except Exception as e:  # límites de uso (429) u otros del proveedor
            if "429" in str(e) or "rate" in str(e).lower():
                time.sleep(25)
                continue
            return None, 0, f"{type(e).__name__}: {str(e)[:120]}"
    return None, 0, "límite de uso persistente"


def summary(d):
    g = lambda k: (d.get(k) or {}).get("valor")  # noqa: E731
    return {"emisor": g("emisor"), "rnc": norm("rnc", g("rnc")), "ncf": norm("ncf", g("ncf")),
            "fecha": g("fecha"), "total": norm("total", (d.get("totales") or {}).get("total"))}


def main(folder: str):
    imgs = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not imgs:
        sys.exit(f"No hay imágenes en {folder}")
    provs = [p for p in ("groq", "claude") if os.environ.get(KEYS[p])]
    for p in ("groq", "claude"):
        if p not in provs:
            print(f"(omitido {p}: falta {KEYS[p]})")
    stats = {p: {"n": 0, "err": 0, "cost": 0.0, "secs": 0.0, "warn": 0, "ok": {}, "tot": {}} for p in provs}
    agree = {"n": 0, "same": 0}

    for img_path in imgs:
        img = img_path.read_bytes()
        media = sniff_media_type(img)
        exp_file = img_path.with_suffix(".expected.json")
        exp = json.loads(exp_file.read_text()) if exp_file.exists() else None
        print(f"\n=== {img_path.name} ===")
        outs = {}
        for p in provs:
            d, secs, err = read(p, img, media)
            st = stats[p]
            st["n"] += 1
            if err:
                st["err"] += 1
                print(f"  [{p}] ERROR: {err}")
                continue
            u = d["usage"]
            cost = (u["input"] * PRICES[p][0] + u["output"] * PRICES[p][1]) / 1e6
            st["cost"] += cost
            st["secs"] += secs
            st["warn"] += len(d["warnings"])
            s = summary(d)
            outs[p] = s
            print(f"  [{p}] {secs:.1f}s  tokens {u['input']}→{u['output']}  ${cost:.5f}  avisos={len(d['warnings'])}")
            print(f"        {s}")
            for w in d["warnings"]:
                print(f"        ! {w}")
            if exp:
                for k, v in exp.items():
                    hit = norm(k, v) == s.get(k) if k != "fecha" else v == s.get(k)
                    st["ok"][k] = st["ok"].get(k, 0) + int(hit)
                    st["tot"][k] = st["tot"].get(k, 0) + 1
                    if not hit:
                        print(f"        ✗ {k}: esperado {v!r}, leyó {s.get(k)!r}")
        if len(outs) == 2:
            agree["n"] += 1
            same = all(outs["groq"][k] == outs["claude"][k] for k in ("rnc", "ncf", "fecha", "total"))
            agree["same"] += int(same)
            if not same:
                print("  ≠ los proveedores NO coinciden en RNC/NCF/fecha/total")

    print("\n===== RESUMEN =====")
    for p, st in stats.items():
        n = max(st["n"] - st["err"], 1)
        line = f"{p:7} lecturas={st['n']} errores={st['err']} costo/factura=${st['cost']/n:.5f} (x2000=${st['cost']/n*2000:.2f}) tiempo medio={st['secs']/n:.1f}s avisos/factura={st['warn']/n:.1f}"
        if st["tot"]:
            line += " | acierto: " + ", ".join(f"{k} {st['ok'][k]}/{st['tot'][k]}" for k in st["tot"])
        print(line)
    if agree["n"]:
        print(f"coinciden en RNC/NCF/fecha/total: {agree['same']}/{agree['n']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/samples")
