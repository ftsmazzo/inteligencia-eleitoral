-- Status canônico dos lotes de contexto BR (fonte-verdade vs mineração).
-- Ausência ≠ zero. Trilha B / bloqueado ficam explícitos.

CREATE SCHEMA IF NOT EXISTS ctl;
CREATE SCHEMA IF NOT EXISTS contexto;

CREATE TABLE IF NOT EXISTS ctl.lote_status (
  id_br           text PRIMARY KEY,
  lote            text NOT NULL,
  tema            text,
  status          text NOT NULL CHECK (status IN (
    'online', 'parcial', 'nucleo', 'bloqueado', 'trilha_b', 'pendente', 'carregando', 'erro'
  )),
  granularidade   text,
  linhas          bigint,
  ano_ref         text,
  fonte           text,
  nota            text,
  atualizado_em   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contexto.indicador_mun (
  ano             smallint NOT NULL,
  cod_ibge        integer NOT NULL REFERENCES ref.municipio (cod_ibge),
  id_indicador    text NOT NULL,
  valor           numeric,
  ds_fonte        text NOT NULL,
  PRIMARY KEY (ano, cod_ibge, id_indicador)
);

CREATE INDEX IF NOT EXISTS idx_ind_mun_ind ON contexto.indicador_mun (id_indicador, ano);

CREATE TABLE IF NOT EXISTS contexto.indicador_uf (
  ano             smallint NOT NULL,
  sg_uf           char(2) NOT NULL,
  id_indicador    text NOT NULL,
  valor           numeric,
  ds_fonte        text NOT NULL,
  PRIMARY KEY (ano, sg_uf, id_indicador)
);

CREATE INDEX IF NOT EXISTS idx_ind_uf_ind ON contexto.indicador_uf (id_indicador, ano);

CREATE TABLE IF NOT EXISTS contexto.indicador_nac (
  ano             smallint NOT NULL,
  id_indicador    text NOT NULL,
  valor           numeric,
  ds_fonte        text NOT NULL,
  PRIMARY KEY (ano, id_indicador)
);

COMMENT ON TABLE ctl.lote_status IS
  'Checklist lote a lote: online|parcial|nucleo|bloqueado|trilha_b. Sem lacuna silenciosa.';
COMMENT ON TABLE contexto.indicador_mun IS
  'Indicadores municipais BR (longo). id_indicador alinhado ao catálogo.';

CREATE OR REPLACE FUNCTION api.status_lotes(
  p_lote text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ctl, pg_temp
AS $$
DECLARE
  v_linhas jsonb;
  v_resumo jsonb;
BEGIN
  SELECT COALESCE(jsonb_object_agg(s.status, s.n), '{}'::jsonb)
    INTO v_resumo
  FROM (
    SELECT status, count(*)::int AS n
    FROM ctl.lote_status
    WHERE p_lote IS NULL OR lote = p_lote
    GROUP BY status
  ) s;

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.lote, t.id_br), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT id_br, lote, tema, status, granularidade, linhas, ano_ref, fonte, nota, atualizado_em
    FROM ctl.lote_status
    WHERE p_lote IS NULL OR lote = p_lote
    ORDER BY lote, id_br
  ) t;

  RETURN jsonb_build_object(
    'status', 'ok',
    'principio', 'acabou = todos os lotes online/nucleo/bloqueado_explicito/trilha_b; sem lacuna silenciosa',
    'resumo', v_resumo,
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.contexto_indicador(
  p_id_indicador text,
  p_ano smallint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, contexto, pg_temp
AS $$
DECLARE
  v_ano smallint;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('contexto_indicador id=%s', p_id_indicador);
  IF p_id_indicador IS NULL OR btrim(p_id_indicador) = '' THEN
    RETURN api._envelope_fora(v_pedido || ' sem id_indicador');
  END IF;

  -- tenta mun primeiro
  SELECT COALESCE(p_ano, MAX(i.ano)) INTO v_ano
  FROM contexto.indicador_mun i WHERE i.id_indicador = p_id_indicador;
  IF v_ano IS NOT NULL THEN
    IF COALESCE(p_nacional, false) IS NOT TRUE AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
      RETURN api._envelope_fora(v_pedido || ' sem uf/cod_ibge/nacional');
    END IF;
    v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
    SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.valor DESC NULLS LAST), '[]'::jsonb)
      INTO v_linhas
    FROM (
      SELECT i.ano, i.cod_ibge, m.nome, m.sg_uf, i.id_indicador, i.valor, i.ds_fonte
      FROM contexto.indicador_mun i
      JOIN ref.municipio m ON m.cod_ibge = i.cod_ibge
      WHERE i.id_indicador = p_id_indicador AND i.ano = v_ano
        AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
        AND (p_cod_ibge IS NULL OR i.cod_ibge = p_cod_ibge)
      ORDER BY i.valor DESC NULLS LAST
      LIMIT v_lim
    ) t;
    IF v_linhas = '[]'::jsonb THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
    END IF;
    RETURN jsonb_build_object('status','ok','nivel','municipio','ano',v_ano,'id_indicador',p_id_indicador,'linhas',v_linhas);
  END IF;

  -- UF
  SELECT COALESCE(p_ano, MAX(i.ano)) INTO v_ano
  FROM contexto.indicador_uf i WHERE i.id_indicador = p_id_indicador;
  IF v_ano IS NOT NULL THEN
    IF COALESCE(p_nacional, false) IS NOT TRUE AND p_uf IS NULL THEN
      RETURN api._envelope_fora(v_pedido || ' sem uf/nacional');
    END IF;
    v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
    SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.valor DESC NULLS LAST), '[]'::jsonb)
      INTO v_linhas
    FROM (
      SELECT i.ano, i.sg_uf, i.id_indicador, i.valor, i.ds_fonte
      FROM contexto.indicador_uf i
      WHERE i.id_indicador = p_id_indicador AND i.ano = v_ano
        AND (p_uf IS NULL OR api.uf_match(p_uf, i.sg_uf))
      ORDER BY i.valor DESC NULLS LAST
      LIMIT v_lim
    ) t;
    IF v_linhas = '[]'::jsonb THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
    END IF;
    RETURN jsonb_build_object('status','ok','nivel','uf','ano',v_ano,'id_indicador',p_id_indicador,'linhas',v_linhas);
  END IF;

  -- nacional
  SELECT COALESCE(p_ano, MAX(i.ano)) INTO v_ano
  FROM contexto.indicador_nac i WHERE i.id_indicador = p_id_indicador;
  IF v_ano IS NOT NULL THEN
    SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
    FROM (
      SELECT i.ano, i.id_indicador, i.valor, i.ds_fonte
      FROM contexto.indicador_nac i
      WHERE i.id_indicador = p_id_indicador AND i.ano = v_ano
    ) t;
    RETURN jsonb_build_object('status','ok','nivel','nacional','ano',v_ano,'id_indicador',p_id_indicador,'linhas',v_linhas);
  END IF;

  RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
END;
$$;

REVOKE ALL ON FUNCTION api.status_lotes(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.contexto_indicador(text, smallint, text, integer, boolean, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.status_lotes(text) TO agente;
GRANT EXECUTE ON FUNCTION api.contexto_indicador(text, smallint, text, integer, boolean, integer) TO agente;
GRANT SELECT ON ctl.lote_status TO agente;
GRANT SELECT ON contexto.indicador_mun TO agente;
GRANT SELECT ON contexto.indicador_uf TO agente;
GRANT SELECT ON contexto.indicador_nac TO agente;
