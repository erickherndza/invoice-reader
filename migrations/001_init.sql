-- Historial de lecturas. No se guarda la imagen, solo el JSON extraído.
CREATE TABLE IF NOT EXISTS invoices (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner       text        NOT NULL,            -- sha256(API key)[:32]; nunca la clave en claro
    provider    text        NOT NULL,
    data        jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS invoices_owner_created_idx ON invoices (owner, created_at DESC);

-- Rate limit compartido entre workers y reinicios.
CREATE TABLE IF NOT EXISTS rate_hits (
    owner text        NOT NULL,
    ts    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rate_hits_owner_ts_idx ON rate_hits (owner, ts);
