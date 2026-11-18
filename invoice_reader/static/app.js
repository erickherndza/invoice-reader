(() => {
'use strict';

const KEY_STORE = 'ir_api_key', RECENT_STORE = 'ir_recent', MAX_RECENT = 30;
const app = document.getElementById('app');
const fileInput = document.getElementById('file');
const SVG = 'http://www.w3.org/2000/svg';

/* ───────── utilidades ───────── */
// Todo el contenido que viene del modelo se inserta con textContent/value: jamás como HTML.
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'text') el.textContent = v;
    else if (k === 'style') el.style.cssText = v; // CSSOM: permitido por la CSP (setAttribute('style') no)
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
}
function icon(paths, size = 24, stroke = '#fff', sw = 2) {
  const s = document.createElementNS(SVG, 'svg');
  for (const [k, v] of Object.entries({ width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke, 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) s.setAttribute(k, v);
  for (const { t, ...a } of paths) { const p = document.createElementNS(SVG, t || 'path'); for (const [k, v] of Object.entries(a)) p.setAttribute(k, v); s.append(p); }
  return s;
}
const I = {
  camera: (c) => icon([{ d: 'M4 8h3l2-3h6l2 3h3v11H4z' }, { t: 'circle', cx: 12, cy: 13, r: 3.5 }], 26, c),
  gallery: () => icon([{ t: 'rect', x: 3, y: 4, width: 18, height: 16, rx: 2 }, { t: 'circle', cx: 9, cy: 10, r: 2 }, { d: 'M21 17l-5-5-9 8' }]),
  flash: () => icon([{ d: 'M13 3L5 14h6l-1 7 8-11h-6z' }]),
  back: () => icon([{ d: 'M15 5l-7 7 7 7' }], 24, '#14213D', 2.2),
  warn: () => icon([{ d: 'M12 3l10 18H2z' }, { d: 'M12 10v5M12 18v.5' }], 20, '#B42318', 2.2),
  check: () => icon([{ d: 'M5 12.5l4.5 4.5L19 7.5' }], 44, '#0B6E4F', 2.5),
};
const cents = (s) => { const n = parseFloat(String(s ?? '').replace(/,/g, '')); return Number.isFinite(n) ? Math.round(n * 100) : null; };
const money = (c) => 'RD$ ' + (c / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const str = (v) => (v == null ? '' : String(v));
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date();
  return d.getDate() + ' ' + MESES[d.getMonth()];
}
const getKey = () => localStorage.getItem(KEY_STORE) || '';
const recents = () => { try { return JSON.parse(localStorage.getItem(RECENT_STORE)) || []; } catch { return []; } };

/* ───────── estado ───────── */
let keyMsg = '', screen = 'home', stream = null, record = null, procState = null, procRun = 0, lastBlob = null;
const go = (s) => { stopCamera(); screen = s; render(); };

function render() {
  app.replaceChildren(({ key: vKey, home: vHome, capture: vCapture, proc: vProc, review: vReview, saved: vSaved })[screen]());
}

/* ───────── acceso (API key) ───────── */
function vKey() {
  const input = h('input', { class: 'fld', id: 'k', type: 'password', autocomplete: 'off', value: '' });
  const msg = h('div', { class: 'fnote low', role: 'alert', text: keyMsg });
  keyMsg = '';
  const save = () => {
    const v = input.value.trim();
    if (!v) { msg.textContent = 'Escribe tu clave de acceso.'; return; }
    localStorage.setItem(KEY_STORE, v); go('home');
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
  return h('div', { class: 'screen' },
    h('div', { class: 'head' }, h('h1', { class: 'title', text: 'Invoice Reader' }), h('p', { class: 'sub', text: 'Introduce la clave de acceso de tu servicio para empezar.' })),
    h('div', { class: 'key-wrap' },
      h('label', { class: 'lbl', for: 'k', text: 'Clave de acceso (API key)' }), input, msg,
      h('button', { class: 'btn', onclick: save, text: 'Entrar' }),
      h('p', { class: 'note', text: 'Se guarda solo en este dispositivo.' })));
}

/* ───────── inicio ───────── */
function vHome() {
  if (!getKey()) { screen = 'key'; return vKey(); }
  const list = recents();
  return h('div', { class: 'screen' },
    h('div', { class: 'head' }, h('h1', { class: 'title', text: 'Facturas' }), h('p', { class: 'sub', text: 'Toma una foto y revisa los datos antes de guardar.' })),
    h('div', { class: 'actions' },
      h('button', { class: 'btn btn-xl', onclick: () => go('capture') }, I.camera('#fff'), 'Escanear factura'),
      h('button', { class: 'btn-line', onclick: () => fileInput.click(), text: 'Subir desde la galería' })),
    h('div', { class: 'list-h eyebrow', text: 'Recientes' }),
    h('div', { class: 'list' },
      list.length ? list.map((r) => h('div', { class: 'card' },
        h('div', { class: 'grow' }, h('div', { class: 'nm', text: r.name }), h('div', { class: 'dt', text: r.date + ' · ' + r.total })),
        h('span', { class: 'chip ' + (r.issues ? 'pend' : 'ok'), text: r.issues ? 'Por revisar' : 'Revisada' })))
        : h('div', { class: 'empty', text: 'Aún no hay facturas. Escanea la primera.' })),
    h('div', { class: 'foot-link' }, h('button', { class: 'btn-link', onclick: () => { localStorage.removeItem(KEY_STORE); go('key'); }, text: 'Cambiar clave de acceso' })));
}

/* ───────── captura ───────── */
function stopCamera() { if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; } }

function vCapture() {
  const frame = h('div', { class: 'frame' });
  const mock = h('div', { class: 'paper-mock' }, h('div', { class: 'ln', style: 'height:14px;width:60%;background:#BDB8AB' }), h('div', { class: 'ln', style: 'width:40%' }), h('div', { class: 'ln', style: 'width:80%;margin-top:14px' }), h('div', { class: 'ln', style: 'width:70%' }), h('div', { class: 'ln', style: 'width:75%' }));
  const tip = h('p', { class: 'cam-tip', text: 'Buena luz, sin sombras y con el papel plano. Se leen mejor RNC, NCF y totales.' });
  const flash = h('button', { class: 'sq', 'aria-label': 'Flash', disabled: true }, I.flash());
  const shutter = h('button', { class: 'shutter', 'aria-label': 'Tomar foto' });
  frame.append(mock, ...['tl', 'tr', 'bl', 'br'].map((c) => h('div', { class: 'corner c-' + c })));
  let video = null, torch = false;

  shutter.addEventListener('click', () => {
    if (!video || !video.videoWidth) { fileInput.click(); return; }
    const c = document.createElement('canvas');
    c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext('2d').drawImage(video, 0, 0);
    c.toBlob((b) => b && startProcessing(b), 'image/jpeg', 0.9);
  });

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } }, audio: false }).then((s) => {
      if (screen !== 'capture') { s.getTracks().forEach((t) => t.stop()); return; }
      stream = s;
      video = h('video', { autoplay: true, playsinline: true, muted: true, 'aria-label': 'Vista de la cámara' });
      video.srcObject = s; video.muted = true;
      frame.prepend(video); mock.remove();
      const track = s.getVideoTracks()[0];
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (caps.torch) {
        flash.disabled = false;
        flash.addEventListener('click', () => { torch = !torch; track.applyConstraints({ advanced: [{ torch }] }).catch(() => {}); });
      }
    }).catch(() => { tip.textContent = 'No se pudo abrir la cámara. Usa la galería (icono de la izquierda).'; });
  } else {
    tip.textContent = 'Este navegador no permite la cámara aquí (requiere HTTPS). Usa la galería.';
  }

  return h('div', { class: 'screen cam' },
    h('div', { class: 'cam-top' }, h('button', { class: 'cancel', onclick: () => go('home'), text: 'Cancelar' }), h('span', { text: 'Encuadra toda la factura' }), h('i')),
    h('div', { class: 'cam-mid' }, frame), tip,
    h('div', { class: 'cam-bar' }, h('button', { class: 'sq', 'aria-label': 'Elegir de la galería', onclick: () => fileInput.click() }, I.gallery()), shutter, flash));
}

fileInput.addEventListener('change', () => {
  const f = fileInput.files && fileInput.files[0];
  fileInput.value = '';
  if (f) startProcessing(f);
});

/* ───────── procesar ───────── */
const STEPS = ['Imagen recibida', 'Extrayendo campos', 'Validando totales e ITBIS'];

// Reduce a JPEG ≤1600 px: acelera la subida y evita pasar del límite de 8 MB.
async function prepare(file) {
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
  const c = document.createElement('canvas');
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close && bmp.close();
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('encode'))), 'image/jpeg', 0.85));
}

function vProc() {
  const p = procState;
  const lines = [['60%', 12, '#BDB8AB'], ['40%', 7, '#CFCBC0'], ['80%', 7, '#CFCBC0', 12], ['70%', 7, '#CFCBC0'], ['75%', 7, '#CFCBC0']];
  const sheet = h('div', { class: 'sheet' }, lines.map(([w, ht, bg, mt]) => h('div', { style: `height:${ht}px;width:${w};background:${bg};${mt ? 'margin-top:' + mt + 'px' : ''}` })), p.error ? null : h('div', { class: 'scan' }));
  if (p.error) {
    return h('div', { class: 'screen proc' }, sheet,
      h('h2', { class: 'h2', style: 'margin:28px 0 6px', text: 'No se pudo leer la factura' }),
      h('p', { class: 'note', role: 'alert', style: 'font-size:14px;text-align:center;margin-bottom:16px', text: p.error }),
      h('div', { class: 'err-box' },
        p.retry ? h('button', { class: 'btn', onclick: () => startProcessing(lastBlob), text: 'Reintentar' }) : null,
        h('button', { class: 'btn-line', onclick: () => go('capture'), text: 'Volver a escanear' }),
        h('button', { class: 'btn-link', onclick: () => go('home'), text: 'Ir al inicio' })));
  }
  return h('div', { class: 'screen proc' }, sheet,
    h('h2', { class: 'h2', style: 'margin:28px 0 6px', text: 'Leyendo factura…' }),
    h('p', { class: 'note', style: 'font-size:14px;margin-bottom:24px', text: 'Suele tardar unos segundos.' }),
    h('div', { class: 'steps' }, STEPS.map((label, i) => {
      const done = p.step > i, cur = p.step === i;
      return h('div', { class: 'step', style: 'color:' + (done ? '#0B6E4F' : cur ? '#14213D' : '#6B7385') }, h('b', { text: done ? '✓' : '' }), label);
    })));
}

const ERR = {
  401: 'La clave de acceso no es válida.',
  413: 'La imagen es demasiado grande (máximo 8 MB).',
  415: 'Solo se aceptan imágenes JPEG, PNG o WebP.',
  429: 'Demasiados escaneos seguidos. Espera un minuto.',
  503: 'El servicio de lectura no está disponible o no está configurado.',
  502: 'El servicio de lectura falló. Inténtalo de nuevo.',
};

async function startProcessing(file) {
  const run = ++procRun;
  lastBlob = file;
  procState = { step: 0 };
  go('proc');
  const upd = (p) => { if (run === procRun && screen === 'proc') { procState = p; render(); } };
  try {
    let blob;
    try { blob = await prepare(file); } catch { return upd({ error: 'No se pudo abrir esa imagen (¿formato HEIC?). Prueba con JPEG, PNG o WebP.' }); }
    upd({ step: 1 });
    const fd = new FormData(); fd.append('file', blob, 'factura.jpg');
    let r;
    try { r = await fetch('/v1/invoices/extract', { method: 'POST', headers: { Authorization: 'Bearer ' + getKey() }, body: fd }); }
    catch { return upd({ error: 'Sin conexión con el servicio.', retry: true }); }
    if (r.status === 401) { localStorage.removeItem(KEY_STORE); procRun++; keyMsg = 'La clave de acceso no es válida. Escríbela de nuevo.'; return go('key'); }
    const j = await r.json().catch(() => null);
    if (!r.ok || !j || !j.ok) return upd({ error: ERR[r.status] || (j && j.error) || 'Error inesperado.', retry: r.status === 429 || r.status >= 500 });
    upd({ step: 2 });
    setTimeout(() => { if (run === procRun) { record = fromApi(j.data || {}, j.warnings || []); go('review'); } }, 500);
  } catch { upd({ error: 'Error inesperado.', retry: true }); }
}

function fromApi(d, warnings) {
  const fld = (key, label) => { const o = d[key] && typeof d[key] === 'object' ? d[key] : {}; const sc = Number(o.score); return { key, label, value: str(o.valor), score: Number.isFinite(sc) && o.valor != null ? sc : 0 }; };
  const t = d.totales && typeof d.totales === 'object' ? d.totales : {};
  return {
    fields: [fld('emisor', 'Emisor'), fld('rnc', 'RNC'), fld('ncf', 'NCF'), fld('fecha', 'Fecha')],
    lines: (Array.isArray(d.lineas) ? d.lineas : []).map((l) => ({ desc: str(l.descripcion), qty: Number(l.cantidad) || 0, price: Number(l.precio_unitario) || 0, itbis: l.itbis_pct })),
    totals: { base: str(t.base_imponible), itbis: str(t.itbis), total: str(t.total) },
    extra: warnings.filter((w) => /^(Línea|RNC|NCF|Fecha)/.test(w)),
  };
}

/* ───────── revisar ───────── */
function vReview() {
  const r = record;
  const alert = h('div', { class: 'alert', role: 'alert' });
  const low = h('div', { class: 'lowtxt' });
  const saveBtn = h('button', { class: 'btn' });

  function totalsIssue() {
    const b = cents(r.totals.base), i = cents(r.totals.itbis), t = cents(r.totals.total);
    if (b === null || i === null || t === null) return 'Hay totales incompletos o ilegibles.';
    if (Math.abs(b + i - t) > 2) return 'Base + ITBIS (' + money(b + i) + ') no coincide con el total (' + money(t) + ').';
    return '';
  }
  function derived() {
    const issue = totalsIssue(), n = r.fields.filter((f) => f.score < 0.85).length;
    alert.replaceChildren(I.warn(), h('span', {}, h('b', { text: 'Totales no cuadran. ' }), issue));
    alert.hidden = !issue;
    low.textContent = n + (n === 1 ? ' campo necesita confirmación' : ' campos necesitan confirmación');
    low.hidden = !n;
    saveBtn.textContent = (issue || n) ? 'Guardar con avisos' : 'Confirmar y guardar';
  }

  const fields = r.fields.map((f) => {
    const input = h('input', { class: 'fld', id: 'f-' + f.key, type: 'text', value: f.value, autocomplete: 'off' });
    const note = h('div', { class: 'fnote' });
    const paint = () => {
      const lo = f.score < 0.85;
      input.className = lo ? 'fld low' : 'fld';
      note.className = lo ? 'fnote low' : 'fnote';
      note.textContent = lo ? 'Confirma este dato' : (f.score >= 1 ? 'Confirmado por ti' : 'Lectura confiable');
    };
    input.addEventListener('input', () => { f.value = input.value; f.score = 1; paint(); derived(); });
    paint();
    return h('div', {}, h('label', { class: 'lbl', for: 'f-' + f.key, text: f.label }), input, note);
  });

  const tot = (key, label) => {
    const input = h('input', { class: 'fld', id: 't-' + key, type: 'text', inputmode: 'decimal', value: r.totals[key], autocomplete: 'off' });
    input.addEventListener('input', () => { r.totals[key] = input.value; derived(); });
    return h('div', { class: 'trow' }, h('label', { for: 't-' + key, text: label }), input);
  };

  const body = h('div', { class: 'rev-body' },
    h('p', { class: 'note', text: 'Datos leídos por IA: confírmalos antes de usarlos contablemente.' }),
    alert, low,
    r.extra.map((w) => h('div', { class: 'lowtxt', text: w })),
    fields,
    h('div', { class: 'eyebrow', style: 'margin-top:6px', text: 'Líneas' }),
    h('div', { class: 'lines' }, r.lines.length ? r.lines.map((l) => h('div', { class: 'lrow' },
      h('div', { class: 'grow' }, h('div', { class: 'd', text: l.desc || '(sin descripción)' }), h('div', { class: 'x', text: l.qty + ' × ' + money(Math.round(l.price * 100)) + ' · ITBIS ' + str(l.itbis) + '%' })),
      h('div', { class: 't', text: money(Math.round(l.qty * l.price * 100)) }))) : h('div', { class: 'empty', text: 'No se detectaron líneas.' })),
    h('div', { class: 'eyebrow', style: 'margin-top:6px', text: 'Totales (RD$)' }),
    tot('base', 'Base imponible'), tot('itbis', 'ITBIS'), tot('total', 'Total'));

  saveBtn.addEventListener('click', save);
  derived();
  return h('div', { class: 'screen' },
    h('div', { class: 'rev-top' }, h('button', { class: 'icon-btn', 'aria-label': 'Volver a escanear', onclick: () => go('capture') }, I.back()), h('h2', { class: 'h2', text: 'Revisar datos' })),
    body,
    h('div', { class: 'rev-foot' }, saveBtn, h('button', { class: 'btn-link', onclick: () => go('capture'), text: 'Volver a escanear' })));
}

function save() {
  const r = record, v = Object.fromEntries(r.fields.map((f) => [f.key, f.value]));
  const t = cents(r.totals.total);
  const issues = r.fields.filter((f) => f.score < 0.85).length + (totalsBad(r) ? 1 : 0);
  r.saved = { name: v.emisor || 'Factura', date: shortDate(v.fecha), total: t === null ? '—' : money(t), issues, data: { fields: v, lines: r.lines, totals: r.totals } };
  const list = [r.saved, ...recents()].slice(0, MAX_RECENT).map((x) => ({ name: x.name, date: x.date, total: x.total, issues: x.issues }));
  try { localStorage.setItem(RECENT_STORE, JSON.stringify(list)); } catch { /* almacenamiento lleno: no bloquea */ }
  go('saved');
}
function totalsBad(r) { const b = cents(r.totals.base), i = cents(r.totals.itbis), t = cents(r.totals.total); return b === null || i === null || t === null || Math.abs(b + i - t) > 2; }

/* ───────── guardada + descarga ───────── */
const cell = (v) => { let s = str(v); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
function toCsv(d) {
  const head = ['emisor', 'rnc', 'ncf', 'fecha', 'descripcion', 'cantidad', 'precio_unitario', 'itbis_pct', 'total_linea', 'base_imponible', 'itbis', 'total'];
  const f = d.fields, t = d.totals;
  const rows = (d.lines.length ? d.lines : [{ desc: '', qty: '', price: '', itbis: '' }]).map((l) => [f.emisor, f.rnc, f.ncf, f.fecha, l.desc, l.qty, l.price, l.itbis, l.qty !== '' ? (l.qty * l.price).toFixed(2) : '', t.base, t.itbis, t.total]);
  return '﻿' + [head, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
}
function download() {
  const s = record.saved, name = (s.data.fields.ncf || 'factura').replace(/[^\w-]+/g, '_');
  const url = URL.createObjectURL(new Blob([toCsv(s.data)], { type: 'text/csv;charset=utf-8' }));
  const a = h('a', { href: url, download: name + '.csv' });
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function vSaved() {
  const s = record.saved;
  return h('div', { class: 'screen done' },
    h('div', { class: 'done-ico' }, I.check()),
    h('h2', { class: 'h2-xl', text: 'Factura guardada' }),
    h('p', { text: s.name + ' · ' + s.total }),
    h('div', { class: 'stack' },
      h('button', { class: 'btn', onclick: () => go('capture'), text: 'Escanear otra' }),
      h('button', { class: 'btn-line', onclick: download, text: 'Descargar para Excel (CSV)' }),
      h('button', { class: 'btn-line', onclick: () => go('home'), text: 'Ir al inicio' })));
}

render();
})();
