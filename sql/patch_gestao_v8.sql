-- patch v8: artefatos visuais em analista + alias plano HTML
-- Idempotente.

INSERT INTO ctl.perfil_tool (perfil_id, tool_name)
SELECT p.id, t.tool_name
FROM ctl.perfil p
CROSS JOIN (VALUES
  ('gerar_imagem'),
  ('gerar_mapa_html'),
  ('gerar_plano_html')
) AS t(tool_name)
WHERE p.slug IN ('analista', 'estrategista', 'coordenador')
  AND p.ativo IS TRUE
ON CONFLICT DO NOTHING;
