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

ALTER TABLE ctl.apura_usuario ADD COLUMN IF NOT EXISTS ultima_sessao_id uuid
  REFERENCES ctl.apura_sessao(id) ON DELETE SET NULL;

ALTER TABLE ctl.apura_usuario ADD COLUMN IF NOT EXISTS quota_perguntas_max integer;
ALTER TABLE ctl.apura_usuario ADD COLUMN IF NOT EXISTS quota_perguntas_used integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN ctl.apura_usuario.quota_perguntas_max IS 'NULL = ilimitado. Contas demo novas: tipicamente 5 perguntas.';
COMMENT ON COLUMN ctl.apura_usuario.quota_perguntas_used IS 'Perguntas (turnos user→assistente) já consumidas no demo.';

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

-- Campanhas (isolamento Apura / MCP por cliente)
CREATE TABLE IF NOT EXISTS ctl.campanha (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome       text NOT NULL UNIQUE,
  ativo      boolean NOT NULL DEFAULT true,
  criado_em  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ctl.apura_usuario ADD COLUMN IF NOT EXISTS campanha_id uuid REFERENCES ctl.campanha(id);
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS campanha_id uuid REFERENCES ctl.campanha(id);
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS nome text;
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS telefone text;
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS apura_usuario_id uuid REFERENCES ctl.apura_usuario(id);

CREATE INDEX IF NOT EXISTS idx_mcp_token_email ON ctl.mcp_token (lower(email)) WHERE email IS NOT NULL;

-- Log de solicitações de cadastro (auto-aprovação)
CREATE TABLE IF NOT EXISTS ctl.cadastro_request (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text NOT NULL,
  nome           text NOT NULL,
  telefone       text,
  campanha_id    uuid REFERENCES ctl.campanha(id),
  status         text NOT NULL DEFAULT 'pendente',
  token_gerado   text,
  token_entregue boolean NOT NULL DEFAULT false,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  aprovado_em    timestamptz
);

CREATE INDEX IF NOT EXISTS idx_cadastro_request_email ON ctl.cadastro_request (lower(email), criado_em DESC);

COMMENT ON TABLE ctl.cadastro_request IS 'Auditoria de cadastros Apura via /apura/cadastro (auto-aprovação).';
COMMENT ON COLUMN ctl.cadastro_request.status IS 'pendente | aprovado | recusado';

GRANT SELECT, INSERT, UPDATE ON ctl.campanha TO agente;
GRANT SELECT, INSERT, UPDATE ON ctl.cadastro_request TO agente;
