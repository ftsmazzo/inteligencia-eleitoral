-- Radar v4 — lista de bloqueio de alvos apagados manualmente.
-- Quando o usuário apaga um alvo (pessoa/adversário/tema/perfil), a chave dele
-- entra aqui. "Preencher da Gestão" (seed aditivo) e a coleta nunca mais
-- recriam esse alvo, mesmo que ele volte a aparecer em blocos de memória
-- (ex.: base_redes) gerados antes de uma correção de escopo.
-- Idempotente. Requer patch_radar.sql.

CREATE TABLE IF NOT EXISTS ctl.radar_alvo_excluido (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  chave text NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (campanha_id, chave)
);

COMMENT ON TABLE ctl.radar_alvo_excluido IS 'Bloqueio permanente de alvos apagados à mão — seed nunca recria';
COMMENT ON COLUMN ctl.radar_alvo_excluido.chave IS 'Identidade normalizada: "{kind}:nome:{nome_sem_acento}" ou "ig:{handle_sem_acento}"';

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_alvo_excluido TO agente;
