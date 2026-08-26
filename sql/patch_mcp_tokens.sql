-- Tokens MCP emitidos pela página /guia (além do MCP_TOKEN mestre no EasyPanel).

CREATE TABLE IF NOT EXISTS ctl.mcp_token (
  token       text PRIMARY KEY,
  rotulo      text NOT NULL DEFAULT '',
  criado_em   timestamptz NOT NULL DEFAULT now(),
  ativo       boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_mcp_token_ativo ON ctl.mcp_token (ativo) WHERE ativo;

COMMENT ON TABLE ctl.mcp_token IS 'Tokens de acesso MCP emitidos pelo guia; MCP_TOKEN mestre continua válido.';
