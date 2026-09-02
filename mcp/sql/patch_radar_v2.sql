-- Radar v2 — alvos PULSO (pessoa/adversario/tema/perfil) + config + item.entity_kind
-- Idempotente. Requer patch_radar.sql base + ctl.campanha.

-- Ampliar kinds (drop check antigo se existir)
ALTER TABLE ctl.radar_alvo DROP CONSTRAINT IF EXISTS radar_alvo_kind_check;
ALTER TABLE ctl.radar_alvo
  ADD CONSTRAINT radar_alvo_kind_check
  CHECK (kind IN ('pessoa', 'adversario', 'tema', 'perfil'));

ALTER TABLE ctl.radar_alvo ADD COLUMN IF NOT EXISTS papel text;
ALTER TABLE ctl.radar_alvo ADD COLUMN IF NOT EXISTS notas text NOT NULL DEFAULT '';
ALTER TABLE ctl.radar_alvo ADD COLUMN IF NOT EXISTS prioridade smallint NOT NULL DEFAULT 5;

COMMENT ON COLUMN ctl.radar_alvo.kind IS 'pessoa|adversario|tema|perfil (Instagram)';
COMMENT ON COLUMN ctl.radar_alvo.is_own IS 'TRUE = Instagram oficial da campanha → Mix/Termômetro';
COMMENT ON COLUMN ctl.radar_alvo.papel IS 'proprio|adversario|aliado|tema|cenario (rotulo UI)';

ALTER TABLE ctl.radar_item ADD COLUMN IF NOT EXISTS entity_kind text;

ALTER TABLE ctl.radar_analise ADD COLUMN IF NOT EXISTS action_ignore text;
ALTER TABLE ctl.radar_analise ADD COLUMN IF NOT EXISTS action_monitor text;

CREATE TABLE IF NOT EXISTS ctl.radar_config (
  campanha_id     uuid PRIMARY KEY REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  candidato_nome  text NOT NULL DEFAULT '',
  uf              char(2),
  cargo           text,
  notas           text NOT NULL DEFAULT '',
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ctl.radar_config IS 'Config da campanha no Radar (candidato monitorado, UF, cargo).';

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_config TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_alvo TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_item TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_analise TO agente;
