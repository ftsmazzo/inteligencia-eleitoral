-- patch_gestao_v5.sql · Apura multiagente (perfis + contatos/tarefas + tools novas)
-- Idempotente.

-- ---------------------------------------------------------------------------
-- Contatos e tarefas operacionais por campanha
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ctl.campanha_contato (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id UUID NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  papel TEXT,
  telefone TEXT,
  email TEXT,
  notas TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campanha_contato_campanha
  ON ctl.campanha_contato (campanha_id);

CREATE TABLE IF NOT EXISTS ctl.campanha_tarefa (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id UUID NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  titulo TEXT NOT NULL,
  descricao TEXT,
  status TEXT NOT NULL DEFAULT 'aberta',
  criado_por UUID REFERENCES ctl.apura_usuario(id) ON DELETE SET NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campanha_tarefa_campanha
  ON ctl.campanha_tarefa (campanha_id, status);

-- ---------------------------------------------------------------------------
-- Reinterpretar perfis (nomes + descrições comportamentais)
-- ---------------------------------------------------------------------------
UPDATE ctl.perfil SET
  nome = 'Operacional',
  descricao = 'Resumo, contatos e tarefas. Poucas tools. Sem protocolo Airy.',
  atualizado_em = now()
WHERE slug = 'consultor_minimo';

UPDATE ctl.perfil SET
  nome = 'Analista',
  descricao = 'Inteligência com cifra + leitura. War-room curto. Sem Matriz Airy.',
  atualizado_em = now()
WHERE slug = 'analista';

UPDATE ctl.perfil SET
  nome = 'Estrategista',
  descricao = 'Missão completa + protocolo Airy Eleitoral + clima/acervo + capacidades avançadas.',
  atualizado_em = now()
WHERE slug = 'estrategista';

UPDATE ctl.perfil SET
  descricao = 'Mesmas tools do estrategista; poder extra é gestão da campanha.',
  atualizado_em = now()
WHERE slug = 'coordenador';

-- ---------------------------------------------------------------------------
-- Tools novas por perfil
-- ---------------------------------------------------------------------------
WITH p AS (
  SELECT id, slug FROM ctl.perfil WHERE slug IN (
    'consultor_minimo', 'analista', 'estrategista', 'coordenador'
  )
),
ops AS (
  SELECT unnest(ARRAY[
    'operacional_contato',
    'operacional_tarefa'
  ]) AS tool_name
),
analista_extra AS (
  SELECT unnest(ARRAY[
    'pesquisar_web',
    'ler_pdf',
    'ler_imagem',
    'transcrever_audio',
    'consultar_clima'
  ]) AS tool_name
),
estrategista_extra AS (
  SELECT unnest(ARRAY[
    'gerar_imagem',
    'gerar_mapa_html'
  ]) AS tool_name
),
desired AS (
  SELECT p.id AS perfil_id, t.tool_name
  FROM p JOIN ops t ON p.slug = 'consultor_minimo'
  UNION ALL
  SELECT p.id, t.tool_name FROM p JOIN ops t ON p.slug IN ('analista', 'estrategista', 'coordenador')
  UNION ALL
  SELECT p.id, t.tool_name FROM p JOIN analista_extra t ON p.slug IN ('analista', 'estrategista', 'coordenador')
  UNION ALL
  SELECT p.id, t.tool_name FROM p JOIN estrategista_extra t ON p.slug IN ('estrategista', 'coordenador')
)
INSERT INTO ctl.perfil_tool (perfil_id, tool_name)
SELECT DISTINCT perfil_id, tool_name FROM desired
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.campanha_contato TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.campanha_tarefa TO agente;
