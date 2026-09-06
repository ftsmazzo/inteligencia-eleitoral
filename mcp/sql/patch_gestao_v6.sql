-- Modelos OpenRouter por função (custo × qualidade).
-- Orquestração/tools → Gemini Flash/Pro; texto final → Anthropic Sonnet.
-- Reaplicável: força UPDATE nos perfis sistema.

UPDATE ctl.perfil SET
  modelo_orquestrador = 'google/gemini-2.5-flash-lite',
  modelo_redator = 'anthropic/claude-haiku-4.5',
  atualizado_em = now()
WHERE slug = 'consultor_minimo';

UPDATE ctl.perfil SET
  modelo_orquestrador = 'google/gemini-2.5-flash',
  modelo_redator = 'anthropic/claude-sonnet-4.6',
  atualizado_em = now()
WHERE slug = 'analista';

UPDATE ctl.perfil SET
  modelo_orquestrador = 'google/gemini-2.5-pro',
  modelo_redator = 'anthropic/claude-sonnet-4.6',
  atualizado_em = now()
WHERE slug IN ('estrategista', 'coordenador');
