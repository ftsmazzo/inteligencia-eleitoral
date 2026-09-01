-- Nominata: cod_ibge em cargo de esfera geral filtrava domicílio (quase sempre NULL) → falso vazio.

CREATE OR REPLACE FUNCTION api.nominata(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_sq_candidato bigint DEFAULT NULL,
  p_nr_candidato integer DEFAULT NULL,
  p_nm_urna text DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_esfera text;
  v_fora jsonb;
  v_tse integer;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_nota text := NULL;
BEGIN
  v_pedido := format('nominata ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  SELECT c.esfera INTO v_esfera FROM ref.cargo c WHERE c.cd_cargo = v_cargo;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  IF p_cod_ibge IS NOT NULL THEN
    IF COALESCE(v_esfera, '') <> 'municipal' THEN
      v_nota := format(
        'cod_ibge %s ignorado: nominata de %s (esfera %s) recorta por UF; município citado não filtra chapa.',
        p_cod_ibge, p_cargo, v_esfera
      );
    ELSE
      SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
      IF v_tse IS NULL THEN
        RETURN jsonb_build_object(
          'status', 'vazio',
          'mensagem', 'Município inexistente neste recorte.',
          'linhas', '[]'::jsonb
        );
      END IF;
    END IF;
  END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      c.ano, c.cd_cargo, r.nome AS cargo, c.sg_uf, c.cd_municipio_tse,
      c.sq_candidato, c.nr_candidato, c.nm_urna, c.nm_candidato,
      c.sg_partido, c.nm_coligacao, c.ds_situacao
    FROM eleicao.candidatura c
    JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
    WHERE c.ano = p_ano
      AND c.cd_cargo = v_cargo
      AND (p_uf IS NULL OR api.uf_match(p_uf, c.sg_uf))
      AND (v_tse IS NULL OR c.cd_municipio_tse = v_tse)
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, c.sg_partido))
      AND (p_sq_candidato IS NULL OR c.sq_candidato = p_sq_candidato)
      AND (p_nr_candidato IS NULL OR c.nr_candidato = p_nr_candidato)
      AND (p_nm_urna IS NULL OR c.nm_urna ILIKE '%' || p_nm_urna || '%')
    ORDER BY c.sg_uf, c.nm_urna
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'Dado inexistente neste recorte.',
      'linhas', v_linhas
    ) || CASE WHEN v_nota IS NOT NULL THEN jsonb_build_object('nota_metodologica', v_nota) ELSE '{}'::jsonb END;
  END IF;
  RETURN jsonb_build_object('status', 'ok', 'linhas', v_linhas)
    || CASE WHEN v_nota IS NOT NULL THEN jsonb_build_object('nota_metodologica', v_nota) ELSE '{}'::jsonb END;
END;
$$;

GRANT EXECUTE ON FUNCTION api.nominata(
  smallint, text, text, integer, text, bigint, integer, text, integer
) TO agente;
