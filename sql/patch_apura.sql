-- Apura · painel conversacional (usuários, sessões, mensagens).

CREATE TABLE IF NOT EXISTS ctl.apura_usuario (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  nome          text NOT NULL DEFAULT '',
  senha_hash    text NOT NULL,
  mcp_token     text NOT NULL UNIQUE,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  ativo         boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS ctl.apura_sessao (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id    uuid NOT NULL REFERENCES ctl.apura_usuario(id) ON DELETE CASCADE,
  titulo        text NOT NULL DEFAULT 'Nova conversa',
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ctl.apura_sessao ADD COLUMN IF NOT EXISTS fixada boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_apura_sessao_usuario ON ctl.apura_sessao (usuario_id, atualizado_em DESC);
CREATE INDEX IF NOT EXISTS idx_apura_sessao_fixada ON ctl.apura_sessao (usuario_id, fixada DESC, atualizado_em DESC);

CREATE TABLE IF NOT EXISTS ctl.apura_mensagem (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sessao_id     uuid NOT NULL REFERENCES ctl.apura_sessao(id) ON DELETE CASCADE,
  papel         text NOT NULL CHECK (papel IN ('user', 'assistant', 'system')),
  conteudo      text NOT NULL DEFAULT '',
  dados_json    jsonb,
  criado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_apura_mensagem_sessao ON ctl.apura_mensagem (sessao_id, criado_em);

CREATE TABLE IF NOT EXISTS ctl.apura_skill (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id    uuid NOT NULL REFERENCES ctl.apura_usuario(id) ON DELETE CASCADE,
  nome          text NOT NULL,
  conteudo      text NOT NULL,
  ativo         boolean NOT NULL DEFAULT false,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_apura_skill_usuario ON ctl.apura_skill (usuario_id, ativo);

COMMENT ON TABLE ctl.apura_usuario IS 'Usuários do painel Apura; cada um tem token MCP próprio.';
COMMENT ON TABLE ctl.apura_skill IS 'Skills pessoais: instruções de tom/formato para o redator expert.';

GRANT USAGE ON SCHEMA ctl TO agente;
GRANT SELECT, INSERT, UPDATE ON ctl.apura_usuario TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.apura_sessao TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.apura_mensagem TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.apura_skill TO agente;
