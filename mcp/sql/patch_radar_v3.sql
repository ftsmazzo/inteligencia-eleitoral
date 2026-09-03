-- Radar v3 — palavras-chave nos eixos do Mix (dica ≠ keywords).
-- Idempotente. Requer patch_radar.sql + patch_radar_v2.sql.

ALTER TABLE ctl.radar_eixo ADD COLUMN IF NOT EXISTS keywords text NOT NULL DEFAULT '';

COMMENT ON COLUMN ctl.radar_eixo.hint IS 'Dica / explicação do eixo para a IA classificar o Mix';
COMMENT ON COLUMN ctl.radar_eixo.keywords IS 'Palavras-chave (vírgula) para matching e seed a partir de planos/dossiê';

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_eixo TO agente;
