-- patch_mapa.sql · Módulo Mapa Apura (Amapá)
-- Idempotente. Centroides: dataset municípios BR (IBGE), UF=AP.

CREATE TABLE IF NOT EXISTS ctl.municipio_geo (
  cod_ibge INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  sg_uf CHAR(2) NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lng DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_municipio_geo_uf ON ctl.municipio_geo (sg_uf);

COMMENT ON TABLE ctl.municipio_geo IS
  'Centroides municipais para o módulo Mapa. Indício de posição; não é voto.';

INSERT INTO ctl.municipio_geo (cod_ibge, nome, sg_uf, lat, lng) VALUES
  (1600055, 'Serra do Navio', 'AP', 0.901357, -52.0036),
  (1600105, 'Amapá', 'AP', 2.05267, -50.7957),
  (1600154, 'Pedra Branca do Amapari', 'AP', 0.777424, -51.9503),
  (1600204, 'Calçoene', 'AP', 2.50475, -50.9512),
  (1600212, 'Cutias', 'AP', 0.970761, -50.8005),
  (1600238, 'Ferreira Gomes', 'AP', 0.857256, -51.1795),
  (1600253, 'Itaubal', 'AP', 0.602185, -50.6996),
  (1600279, 'Laranjal do Jari', 'AP', -0.804911, -52.453),
  (1600303, 'Macapá', 'AP', 0.034934, -51.0694),
  (1600402, 'Mazagão', 'AP', -0.11336, -51.2891),
  (1600501, 'Oiapoque', 'AP', 3.84074, -51.8331),
  (1600535, 'Porto Grande', 'AP', 0.71243, -51.4155),
  (1600550, 'Pracuúba', 'AP', 1.74543, -50.7892),
  (1600600, 'Santana', 'AP', -0.045434, -51.1729),
  (1600709, 'Tartarugalzinho', 'AP', 1.50652, -50.9087),
  (1600808, 'Vitória do Jari', 'AP', -0.938, -52.424)
ON CONFLICT (cod_ibge) DO UPDATE SET
  nome = EXCLUDED.nome,
  sg_uf = EXCLUDED.sg_uf,
  lat = EXCLUDED.lat,
  lng = EXCLUDED.lng;

CREATE TABLE IF NOT EXISTS ctl.mapa_nota (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id UUID NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  cod_ibge INTEGER NOT NULL,
  texto TEXT NOT NULL DEFAULT '',
  atualizado_por UUID REFERENCES ctl.apura_usuario(id) ON DELETE SET NULL,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (campanha_id, cod_ibge)
);

CREATE INDEX IF NOT EXISTS idx_mapa_nota_campanha ON ctl.mapa_nota (campanha_id);

CREATE TABLE IF NOT EXISTS ctl.mapa_caravana (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id UUID NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  nome TEXT NOT NULL DEFAULT 'Carreata',
  pontos_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  rota_geojson JSONB,
  criado_por UUID REFERENCES ctl.apura_usuario(id) ON DELETE SET NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mapa_caravana_campanha ON ctl.mapa_caravana (campanha_id);

-- Módulo mapa nas campanhas existentes
INSERT INTO ctl.campanha_modulo (campanha_id, codigo, ativo)
SELECT c.id, 'mapa', true
FROM ctl.campanha c
WHERE NOT EXISTS (
  SELECT 1 FROM ctl.campanha_modulo m
  WHERE m.campanha_id = c.id AND m.codigo = 'mapa'
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.municipio_geo TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.mapa_nota TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.mapa_caravana TO agente;
