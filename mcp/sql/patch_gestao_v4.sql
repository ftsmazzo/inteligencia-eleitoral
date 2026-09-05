-- Gestão v4 · quotas por campanha (shell multi-tenant P5)
-- Idempotente.

ALTER TABLE ctl.campanha
  ADD COLUMN IF NOT EXISTS quota_perguntas_max integer;

COMMENT ON COLUMN ctl.campanha.quota_perguntas_max IS
  'Limite agregado de perguntas da campanha (NULL = ilimitado). Conta user messages dos membros com campanha_ativa/campanha_id = esta.';
