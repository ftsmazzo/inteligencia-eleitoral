-- Tokens MCP emitidos pela página /guia (além do MCP_TOKEN mestre no EasyPanel).

CREATE TABLE IF NOT EXISTS ctl.mcp_token (
  token       text PRIMARY KEY,
  rotulo      text NOT NULL DEFAULT '',
  criado_em   timestamptz NOT NULL DEFAULT now(),
  ativo       boolean NOT NULL DEFAULT true
);

ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS quota_max integer;
ALTER TABLE ctl.mcp_token ADD COLUMN IF NOT EXISTS quota_used integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_mcp_token_ativo ON ctl.mcp_token (ativo) WHERE ativo;

COMMENT ON TABLE ctl.mcp_token IS 'Tokens de acesso MCP emitidos pelo guia; MCP_TOKEN mestre continua válido.';
COMMENT ON COLUMN ctl.mcp_token.quota_max IS 'NULL = ilimitado (token interno/equipe). Demo guia: tipicamente 5.';
COMMENT ON COLUMN ctl.mcp_token.quota_used IS 'Consultas MCP já consumidas (POST /mcp e /v1/*).';

GRANT USAGE ON SCHEMA ctl TO agente;
GRANT SELECT, INSERT, UPDATE ON ctl.mcp_token TO agente;
