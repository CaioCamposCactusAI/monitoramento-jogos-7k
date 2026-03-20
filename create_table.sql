-- Tabela de monitoramento de jogos
CREATE TABLE monitoramento_jogos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    slug TEXT NOT NULL,
    brand TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('on', 'off')),
    motivo TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE (slug, brand)
);

-- Index para consultas filtradas por brand
CREATE INDEX idx_monitoramento_jogos_brand ON monitoramento_jogos (brand);

-- Habilitar RLS (Row Level Security) e permitir acesso via anon key
ALTER TABLE monitoramento_jogos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anon select" ON monitoramento_jogos FOR SELECT USING (true);
CREATE POLICY "Allow anon insert" ON monitoramento_jogos FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon update" ON monitoramento_jogos FOR UPDATE USING (true) WITH CHECK (true);
