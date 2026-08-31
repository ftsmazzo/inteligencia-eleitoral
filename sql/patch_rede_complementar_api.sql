-- API: redes sociais e informações complementares TSE (eleicao.*)

CREATE OR REPLACE FUNCTION api.rede_social(
  p_ano smallint,
  p_sq_candidato bigint,
  p_limite integer DEFAULT 50
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_fora jsonb;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('rede_social ano=%s sq=%s', p_ano, p_sq_candidato);
  v_fora := api._checar_ano(p_ano, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_sq_candidato IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' exige sq_candidato');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 50), 1), 100);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT r.ano, r.sq_candidato, r.nr_ordem, r.ds_url, r.sg_uf
    FROM eleicao.rede_social r
    WHERE r.ano = p_ano
      AND r.sq_candidato = p_sq_candidato
    ORDER BY r.nr_ordem, r.ds_url
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.complementar(
  p_ano smallint,
  p_sq_candidato bigint
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_fora jsonb;
  v_linha jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('complementar ano=%s sq=%s', p_ano, p_sq_candidato);
  v_fora := api._checar_ano(p_ano, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_sq_candidato IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' exige sq_candidato');
  END IF;
  SELECT to_jsonb(t) INTO v_linha
  FROM (
    SELECT
      c.ano, c.sq_candidato, c.sg_uf,
      c.ds_nacionalidade, c.nr_idade_data_posse, c.st_quilombola,
      c.ds_etnia_indigena, c.vr_despesa_max_campanha, c.st_reeleicao,
      c.st_declarar_bens, c.ds_detalhe_situacao_cand, c.ds_situacao_candidato_pleito,
      c.ds_situacao_candidato_urna, c.st_candidato_inserido_urna, c.st_prest_contas,
      c.st_substituido, c.ds_situacao_julgamento, c.ds_situacao_cassacao,
      c.ds_situacao_diploma, c.ds_genero_fefc, c.ds_cor_raca_fefc
    FROM eleicao.candidato_complementar c
    WHERE c.ano = p_ano
      AND c.sq_candidato = p_sq_candidato
    LIMIT 1
  ) t;
  IF v_linha IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', jsonb_build_array(v_linha));
END;
$$;

GRANT EXECUTE ON FUNCTION api.rede_social(smallint, bigint, integer) TO agente;
GRANT EXECUTE ON FUNCTION api.complementar(smallint, bigint) TO agente;
