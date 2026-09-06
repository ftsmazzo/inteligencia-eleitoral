-- Tools: consultar_memoria (estratégias / dossiê / pesquisas sob demanda)
-- Idempotente.

WITH p AS (
  SELECT id, slug FROM ctl.perfil WHERE slug IN (
    'analista', 'estrategista', 'coordenador'
  )
),
desired AS (
  SELECT p.id AS perfil_id, 'consultar_memoria'::text AS tool_name
  FROM p
)
INSERT INTO ctl.perfil_tool (perfil_id, tool_name)
SELECT DISTINCT perfil_id, tool_name FROM desired
ON CONFLICT DO NOTHING;
