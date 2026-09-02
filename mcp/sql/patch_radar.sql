-- Radar (camada C) — isolado por ctl.campanha (uuid). nivel=indicio sempre na API.
-- Idempotente. Requer ctl.campanha (patch_apura).

CREATE TABLE IF NOT EXISTS ctl.radar_alvo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id   uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('pessoa', 'adversario', 'tema', 'perfil')),
  nome          text NOT NULL,
  query_news    text NOT NULL DEFAULT '',
  handle_ig     text,
  is_own        boolean NOT NULL DEFAULT false,
  ativo         boolean NOT NULL DEFAULT true,
  papel         text,
  notas         text NOT NULL DEFAULT '',
  prioridade    smallint NOT NULL DEFAULT 5,
  last_seen_at  timestamptz,
  criado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_radar_alvo_campanha
  ON ctl.radar_alvo (campanha_id) WHERE ativo IS TRUE;

CREATE TABLE IF NOT EXISTS ctl.radar_item (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id   uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  origem        text NOT NULL DEFAULT 'clima' CHECK (origem IN ('clima', 'oficial')),
  canal         text NOT NULL DEFAULT 'news',
  fonte         text,
  url           text,
  titulo        text NOT NULL,
  body          text NOT NULL DEFAULT '',
  published_at  timestamptz NOT NULL DEFAULT now(),
  fingerprint   text NOT NULL,
  entity_name   text,
  entity_kind   text,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (campanha_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_radar_item_campanha_pub
  ON ctl.radar_item (campanha_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_radar_item_origem
  ON ctl.radar_item (campanha_id, origem, published_at DESC);

CREATE TABLE IF NOT EXISTS ctl.radar_analise (
  item_id         uuid PRIMARY KEY REFERENCES ctl.radar_item(id) ON DELETE CASCADE,
  tipo            text,
  urgencia        text,
  polarity        text,
  score           integer,
  risk            text,
  synthesis       text,
  eixo            text,
  model           text,
  action_respond  text,
  action_ignore   text,
  action_monitor  text,
  criado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ctl.radar_eixo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id   uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  name          text NOT NULL,
  hint          text NOT NULL DEFAULT '',
  enabled       boolean NOT NULL DEFAULT true,
  UNIQUE (campanha_id, name)
);

CREATE TABLE IF NOT EXISTS ctl.radar_run (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id   uuid REFERENCES ctl.campanha(id) ON DELETE SET NULL,
  mode          text NOT NULL DEFAULT 'manual',
  ok            integer NOT NULL DEFAULT 0,
  err           text,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);

CREATE INDEX IF NOT EXISTS idx_radar_run_started
  ON ctl.radar_run (started_at DESC);

CREATE TABLE IF NOT EXISTS ctl.radar_config (
  campanha_id     uuid PRIMARY KEY REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  candidato_nome  text NOT NULL DEFAULT '',
  uf              char(2),
  cargo           text,
  notas           text NOT NULL DEFAULT '',
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ctl.radar_item IS 'Stream clima/oficial do Radar; sempre nivel=indicio na API.';
COMMENT ON TABLE ctl.radar_alvo IS 'Alvos: pessoa|adversario|tema|perfil; is_own=IG oficial→Mix.';
COMMENT ON TABLE ctl.radar_config IS 'Candidato monitorado / UF / cargo da campanha no Radar.';

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_alvo TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_item TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_analise TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_eixo TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_run TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_config TO agente;
