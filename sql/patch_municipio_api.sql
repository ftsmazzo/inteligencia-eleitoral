-- Resolver município por nome → cod_ibge (sem exigir IBGE na conversa).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION api.municipio(
  p_nome text,
  p_uf text DEFAULT NULL,
  p_limite integer DEFAULT 10
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, public, pg_temp
AS $$
DECLARE
  v_nome text;
  v_uf text;
  v_lim integer;
  v_linhas jsonb;
BEGIN
  v_nome := NULLIF(btrim(COALESCE(p_nome, '')), '');
  IF v_nome IS NULL OR char_length(v_nome) < 2 THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'Informe o nome do município (mín. 2 caracteres).',
      'linhas', '[]'::jsonb
    );
  END IF;
  v_uf := NULLIF(upper(btrim(COALESCE(p_uf, ''))), '');
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 10), 1), 50);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.score DESC, t.nome), '[]'::jsonb)
  INTO v_linhas
  FROM (
    SELECT
      m.cod_ibge,
      m.cd_municipio_tse,
      m.nome,
      m.sg_uf,
      similarity(lower(m.nome), lower(v_nome))::float AS score
    FROM ref.municipio m
    WHERE (v_uf IS NULL OR m.sg_uf = v_uf)
      AND (
        lower(m.nome) % lower(v_nome)
        OR lower(m.nome) LIKE '%' || lower(v_nome) || '%'
      )
    ORDER BY 5 DESC, m.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', format('Município não encontrado para nome=%s uf=%s.', v_nome, COALESCE(v_uf, '*')),
      'linhas', v_linhas
    );
  END IF;
  RETURN jsonb_build_object('status', 'ok', 'linhas', v_linhas);
END;
$$;

GRANT EXECUTE ON FUNCTION api.municipio(text, text, integer) TO agente;
REVOKE ALL ON FUNCTION api.municipio(text, text, integer) FROM PUBLIC;
