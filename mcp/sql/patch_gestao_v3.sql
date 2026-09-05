-- Gestão v3 · Plataforma multi-campanha + Perfis + auditoria
-- Contrato: docs/CONTRATO-PLATAFORMA-GESTAO.md
-- Idempotente. Requer ctl.campanha + ctl.apura_usuario (patch_apura / gestao).
-- Classificação: interno (ctl.*). E-mails/tokens = sensível em runtime.

-- ---------------------------------------------------------------------------
-- Super gestores (plataforma)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.plataforma_super_gestor (
  email      text PRIMARY KEY,
  nome       text NOT NULL,
  ativo      boolean NOT NULL DEFAULT true,
  criado_em  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ctl.plataforma_super_gestor IS
  'Os 3 super gestores da plataforma Apura. Tudo passa por eles. Sensível: e-mails.';

INSERT INTO ctl.plataforma_super_gestor (email, nome) VALUES
  ('fredmazzo@gmail.com', 'Frederico Mazzo'),
  ('leonardotamburus@gmail.com', 'Leonardo Tamburus'),
  ('aryengracia@gmail.com', 'Ary Engracia')
ON CONFLICT (email) DO UPDATE SET nome = EXCLUDED.nome, ativo = true;

-- ---------------------------------------------------------------------------
-- Perfis (templates de modelo + tools)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.perfil (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                  text NOT NULL UNIQUE,
  nome                  text NOT NULL,
  descricao             text NOT NULL DEFAULT '',
  modelo_orquestrador   text NOT NULL,
  modelo_redator        text NOT NULL,
  quota_perguntas_max   integer,
  ativo                 boolean NOT NULL DEFAULT true,
  sistema               boolean NOT NULL DEFAULT false,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ctl.perfil IS
  'Templates de acesso IA: modelos OpenRouter + allowlist de tools. Editáveis pelos super gestores.';
COMMENT ON COLUMN ctl.perfil.sistema IS 'true = seed oficial; não apagar (pode desativar).';
COMMENT ON COLUMN ctl.perfil.quota_perguntas_max IS 'NULL = ilimitado neste perfil.';

CREATE TABLE IF NOT EXISTS ctl.perfil_tool (
  perfil_id   uuid NOT NULL REFERENCES ctl.perfil(id) ON DELETE CASCADE,
  tool_name   text NOT NULL,
  PRIMARY KEY (perfil_id, tool_name)
);

COMMENT ON TABLE ctl.perfil_tool IS
  'Allowlist de tools MCP/Apura por perfil. Enforcement no servidor obrigatório.';

CREATE INDEX IF NOT EXISTS idx_perfil_tool_name ON ctl.perfil_tool (tool_name);

-- ---------------------------------------------------------------------------
-- Módulos por campanha
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.campanha_modulo (
  campanha_id  uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  codigo       text NOT NULL,
  ativo        boolean NOT NULL DEFAULT true,
  meta_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (campanha_id, codigo)
);

COMMENT ON TABLE ctl.campanha_modulo IS
  'Módulos provisionados na criação da campanha (chat|radar|clima|dados_mcp|gestao_campanha). Virgens até configurados.';
COMMENT ON COLUMN ctl.campanha_modulo.codigo IS
  'chat | radar | clima | dados_mcp | gestao_campanha (+ futuros)';

CREATE INDEX IF NOT EXISTS idx_campanha_modulo_ativo
  ON ctl.campanha_modulo (campanha_id) WHERE ativo;

-- ---------------------------------------------------------------------------
-- Membros (N:N usuário × campanha × perfil)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.campanha_membro (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id      uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  usuario_id       uuid NOT NULL REFERENCES ctl.apura_usuario(id) ON DELETE CASCADE,
  perfil_id        uuid NOT NULL REFERENCES ctl.perfil(id),
  papel_campanha   text NOT NULL DEFAULT 'equipe'
                   CHECK (papel_campanha IN ('coordenador', 'equipe')),
  ativo            boolean NOT NULL DEFAULT true,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (campanha_id, usuario_id)
);

COMMENT ON TABLE ctl.campanha_membro IS
  'Vínculo usuário–campanha com Perfil (modelo/tools) e papel local (coordenador|equipe).';
COMMENT ON COLUMN ctl.campanha_membro.papel_campanha IS
  'coordenador = gestão daquela campanha; equipe = só módulos liberados.';

CREATE INDEX IF NOT EXISTS idx_campanha_membro_usuario
  ON ctl.campanha_membro (usuario_id) WHERE ativo;
CREATE INDEX IF NOT EXISTS idx_campanha_membro_campanha
  ON ctl.campanha_membro (campanha_id) WHERE ativo;

-- Campanha ativa pós-seletor (NULL = ainda não escolheu / super na frota)
ALTER TABLE ctl.apura_usuario
  ADD COLUMN IF NOT EXISTS campanha_ativa_id uuid REFERENCES ctl.campanha(id);

COMMENT ON COLUMN ctl.apura_usuario.campanha_ativa_id IS
  'Campanha escolhida no seletor pós-login. Sem valor: Chat/Radar/Clima indisponíveis.';

-- ---------------------------------------------------------------------------
-- Token MCP no contexto da campanha + perfil
-- ---------------------------------------------------------------------------
ALTER TABLE ctl.mcp_token
  ADD COLUMN IF NOT EXISTS perfil_id uuid REFERENCES ctl.perfil(id);

COMMENT ON COLUMN ctl.mcp_token.perfil_id IS
  'Perfil (tools/modelo) do token de campanha. NULL = legado; runtime deve aplicar default seguro.';

CREATE INDEX IF NOT EXISTS idx_mcp_token_campanha_perfil
  ON ctl.mcp_token (campanha_id, perfil_id)
  WHERE ativo AND campanha_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Auditoria de acesso / ações
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.evento_acesso (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ocorrido_em   timestamptz NOT NULL DEFAULT now(),
  usuario_id    uuid REFERENCES ctl.apura_usuario(id) ON DELETE SET NULL,
  campanha_id   uuid REFERENCES ctl.campanha(id) ON DELETE SET NULL,
  token_rotulo  text,
  acao          text NOT NULL,
  detalhe_json  jsonb NOT NULL DEFAULT '{}'::jsonb,
  ip            text,
  user_agent    text
);

COMMENT ON TABLE ctl.evento_acesso IS
  'Log de acesso e ações (login, troca campanha, CRUD membro, token, liberar, etc.). Interno.';
COMMENT ON COLUMN ctl.evento_acesso.acao IS
  'login|logout|entrar_campanha|criar_campanha|membro_upsert|perfil_update|token_emitir|liberar_equipe|seed_radar|dossie_upload|…';

CREATE INDEX IF NOT EXISTS idx_evento_acesso_quando
  ON ctl.evento_acesso (ocorrido_em DESC);
CREATE INDEX IF NOT EXISTS idx_evento_acesso_usuario
  ON ctl.evento_acesso (usuario_id, ocorrido_em DESC);
CREATE INDEX IF NOT EXISTS idx_evento_acesso_campanha
  ON ctl.evento_acesso (campanha_id, ocorrido_em DESC);

-- ---------------------------------------------------------------------------
-- Seed de Perfis
-- ---------------------------------------------------------------------------
INSERT INTO ctl.perfil (slug, nome, descricao, modelo_orquestrador, modelo_redator, sistema)
VALUES
  (
    'consultor_minimo',
    'Consultor mínimo',
    'Leitura leve: catálogo, município, nominata. Modelos baratos.',
    'openai/gpt-4o-mini',
    'openai/gpt-4o-mini',
    true
  ),
  (
    'analista',
    'Analista',
    'Cifras TSE, contexto social/MDS, Parlamento, cruzamentos. Sem acervo/clima.',
    'openai/gpt-4o-mini',
    'openai/gpt-4o',
    true
  ),
  (
    'estrategista',
    'Estrategista',
    'Analista + acervo + clima. Modelos mais capazes.',
    'anthropic/claude-sonnet-4',
    'openai/gpt-4o',
    true
  ),
  (
    'coordenador',
    'Coordenador',
    'Mesmas tools do estrategista; poder extra é gestão da campanha (papel_campanha).',
    'anthropic/claude-sonnet-4',
    'openai/gpt-4o',
    true
  )
ON CONFLICT (slug) DO UPDATE SET
  nome = EXCLUDED.nome,
  descricao = EXCLUDED.descricao,
  atualizado_em = now();

-- Tools por perfil (reaplicável)
WITH p AS (
  SELECT id, slug FROM ctl.perfil WHERE slug IN (
    'consultor_minimo', 'analista', 'estrategista', 'coordenador'
  )
),
tools_minimo AS (
  SELECT unnest(ARRAY[
    'consultar_catalogo',
    'consultar_municipio',
    'consultar_nominata'
  ]) AS tool_name
),
tools_analista AS (
  SELECT tool_name FROM tools_minimo
  UNION ALL
  SELECT unnest(ARRAY[
    'consultar_votacao',
    'consultar_comparecimento',
    'consultar_eleitorado',
    'consultar_coligacao',
    'consultar_vagas',
    'consultar_bem',
    'consultar_rede_social',
    'consultar_complementar',
    'consultar_receita',
    'consultar_despesa',
    'consultar_contas_resumo',
    'consultar_eleitos',
    'consultar_populacao',
    'consultar_cadunico',
    'consultar_bolsa_familia',
    'consultar_deputados_casa',
    'consultar_senadores',
    'consultar_proposicoes',
    'consultar_votos_camara',
    'consultar_depara_parlamentar',
    'consultar_linha_temporal',
    'consultar_cruzamento_social',
    'consultar_mandato_urna'
  ])
),
tools_estrategista AS (
  SELECT tool_name FROM tools_analista
  UNION ALL
  SELECT unnest(ARRAY[
    'consultar_acervo',
    'consultar_acervo_comparar',
    'consultar_clima'
  ])
),
desired AS (
  SELECT p.id AS perfil_id, t.tool_name
  FROM p
  JOIN tools_minimo t ON p.slug = 'consultor_minimo'
  UNION ALL
  SELECT p.id, t.tool_name FROM p
  JOIN tools_analista t ON p.slug = 'analista'
  UNION ALL
  SELECT p.id, t.tool_name FROM p
  JOIN tools_estrategista t ON p.slug IN ('estrategista', 'coordenador')
)
INSERT INTO ctl.perfil_tool (perfil_id, tool_name)
SELECT DISTINCT perfil_id, tool_name FROM desired
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Provisionar módulos em campanhas já existentes
-- ---------------------------------------------------------------------------
INSERT INTO ctl.campanha_modulo (campanha_id, codigo, ativo)
SELECT c.id, m.codigo, true
FROM ctl.campanha c
CROSS JOIN (
  VALUES
    ('chat'),
    ('radar'),
    ('clima'),
    ('dados_mcp'),
    ('gestao_campanha')
) AS m(codigo)
ON CONFLICT (campanha_id, codigo) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Backfill membros a partir de campanha_id legado
-- ---------------------------------------------------------------------------
INSERT INTO ctl.campanha_membro (campanha_id, usuario_id, perfil_id, papel_campanha, ativo)
SELECT
  u.campanha_id,
  u.id,
  CASE
    WHEN lower(COALESCE(u.papel, 'equipe')) = 'coordenador'
      THEN (SELECT id FROM ctl.perfil WHERE slug = 'coordenador')
    ELSE (SELECT id FROM ctl.perfil WHERE slug = 'analista')
  END,
  CASE
    WHEN lower(COALESCE(u.papel, 'equipe')) = 'coordenador' THEN 'coordenador'
    ELSE 'equipe'
  END,
  COALESCE(u.ativo, true)
FROM ctl.apura_usuario u
WHERE u.campanha_id IS NOT NULL
ON CONFLICT (campanha_id, usuario_id) DO NOTHING;

UPDATE ctl.apura_usuario u
SET campanha_ativa_id = u.campanha_id
WHERE u.campanha_ativa_id IS NULL
  AND u.campanha_id IS NOT NULL;

UPDATE ctl.mcp_token t
SET perfil_id = (SELECT id FROM ctl.perfil WHERE slug = 'analista')
WHERE t.campanha_id IS NOT NULL
  AND t.perfil_id IS NULL;

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.plataforma_super_gestor TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.perfil TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.perfil_tool TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.campanha_modulo TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.campanha_membro TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.evento_acesso TO agente;
