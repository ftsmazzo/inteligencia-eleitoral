-- PIB municipal IBGE (contexto econômico; não urna).
-- SIDRA 5938 — Produto Interno Bruto dos Municípios (âmbito BR).

CREATE SCHEMA IF NOT EXISTS contexto;

CREATE TABLE IF NOT EXISTS contexto.pib_mun (
  ano                  smallint NOT NULL,
  cod_ibge             integer NOT NULL REFERENCES ref.municipio (cod_ibge),
  vr_pib_mil           numeric(18, 2),  -- var 37; unidade: R$ mil
  vr_pib_per_capita    numeric(18, 2),  -- var 543; unidade: R$
  ds_fonte             text NOT NULL DEFAULT 'ibge_sidra_5938',
  PRIMARY KEY (ano, cod_ibge)
);

CREATE INDEX IF NOT EXISTS idx_pib_ano ON contexto.pib_mun (ano);

COMMENT ON TABLE contexto.pib_mun IS
  'PIB municipal IBGE SIDRA 5938 (BR). vr_pib_mil em R$ mil; per capita em R$. Ausência ≠ zero.';

CREATE OR REPLACE FUNCTION api.pib(
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
  v_total numeric;
BEGIN
  v_pedido := format('pib ano=%s', p_ano);
  SELECT COALESCE(p_ano, MAX(p.ano)) INTO v_ano FROM contexto.pib_mun p;
  IF v_ano IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF p_ano IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM contexto.pib_mun p WHERE p.ano = p_ano
  ) THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE
     AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' sem uf/cod_ibge/nacional');
  END IF;
  IF p_cod_ibge IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge
  ) THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);

  SELECT COALESCE(SUM(p.vr_pib_mil), 0) INTO v_total
  FROM contexto.pib_mun p
  JOIN ref.municipio m ON m.cod_ibge = p.cod_ibge
  WHERE p.ano = v_ano
    AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
    AND (p_cod_ibge IS NULL OR p.cod_ibge = p_cod_ibge);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.vr_pib_mil DESC NULLS LAST, t.nome), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      p.ano, p.cod_ibge, m.nome, m.sg_uf,
      p.vr_pib_mil, p.vr_pib_per_capita, p.ds_fonte
    FROM contexto.pib_mun p
    JOIN ref.municipio m ON m.cod_ibge = p.cod_ibge
    WHERE p.ano = v_ano
      AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
      AND (p_cod_ibge IS NULL OR p.cod_ibge = p_cod_ibge)
    ORDER BY p.vr_pib_mil DESC NULLS LAST, m.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'ano', v_ano,
    'unidade_pib', 'R$ mil',
    'unidade_per_capita', 'R$',
    'vr_pib_mil_total', v_total,
    'ds_fonte', 'ibge_sidra_5938',
    'nota_metodologica', 'PIB dos Municípios IBGE (SIDRA 5938), âmbito Brasil; contexto, não urna',
    'linhas', v_linhas
  );
END;
$$;

REVOKE ALL ON FUNCTION api.pib(smallint, text, integer, boolean, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.pib(smallint, text, integer, boolean, integer) TO agente;
