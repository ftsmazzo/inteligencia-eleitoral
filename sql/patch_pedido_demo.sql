-- Pedidos de demo da landing (formulário → e-mail + registro).

CREATE TABLE IF NOT EXISTS ctl.pedido_demo (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome        text NOT NULL,
  email       text NOT NULL,
  empresa     text NOT NULL DEFAULT '',
  mensagem    text NOT NULL DEFAULT '',
  origem      text NOT NULL DEFAULT 'landing',
  criado_em   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pedido_demo_criado ON ctl.pedido_demo (criado_em DESC);

COMMENT ON TABLE ctl.pedido_demo IS 'Leads do formulário de demo da landing.';

GRANT USAGE ON SCHEMA ctl TO agente;
GRANT SELECT, INSERT ON ctl.pedido_demo TO agente;
