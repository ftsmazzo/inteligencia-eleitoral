-- Comércio exterior por UF (ComexStat MDIC; contexto, não urna).

CREATE SCHEMA IF NOT EXISTS contexto;

CREATE TABLE IF NOT EXISTS contexto.comex_uf (
  ano            smallint NOT NULL,
  sg_uf          char(2) NOT NULL,
  nm_uf_fonte    text,
  fluxo          text NOT NULL CHECK (fluxo IN ('export', 'import')),
  vr_fob_usd     numeric(20, 2),
  qt_kg          numeric(20, 3),
  ds_fonte       text NOT NULL DEFAULT 'comexstat_mdic',
  PRIMARY KEY (ano, sg_uf, fluxo)
);

CREATE INDEX IF NOT EXISTS idx_comex_ano ON contexto.comex_uf (ano);

COMMENT ON TABLE contexto.comex_uf IS
  'Export/import FOB (USD) e kg por UF — ComexStat MDIC. Âmbito BR. UF ND = sg_uf XX. Ausência ≠ zero.';

CREATE OR REPLACE FUNCTION api.comex(
  p_ano smallint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_fluxo text DEFAULT NULL,
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
  v_fluxo text;
BEGIN
  v_pedido := format('comex ano=%s', p_ano);
  SELECT COALESCE(p_ano, MAX(c.ano)) INTO v_ano FROM contexto.comex_uf c;
  IF v_ano IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF p_ano IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM contexto.comex_uf c WHERE c.ano = p_ano
  ) THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE AND p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' sem uf/nacional');
  END IF;
  v_fluxo := NULLIF(lower(btrim(COALESCE(p_fluxo, ''))), '');
  IF v_fluxo IS NOT NULL AND v_fluxo NOT IN ('export', 'import') THEN
    RETURN api._envelope_fora(v_pedido || ' fluxo deve ser export|import');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.vr_fob_usd DESC NULLS LAST, t.sg_uf, t.fluxo), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT c.ano, c.sg_uf, c.nm_uf_fonte, c.fluxo, c.vr_fob_usd, c.qt_kg, c.ds_fonte
    FROM contexto.comex_uf c
    WHERE c.ano = v_ano
      AND (p_uf IS NULL OR api.uf_match(p_uf, c.sg_uf) OR (upper(btrim(p_uf)) IN ('XX','ND') AND c.sg_uf = 'XX'))
      AND (v_fluxo IS NULL OR c.fluxo = v_fluxo)
    ORDER BY c.vr_fob_usd DESC NULLS LAST, c.sg_uf, c.fluxo
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'ano', v_ano,
    'unidade_fob', 'USD',
    'ds_fonte', 'comexstat_mdic',
    'nota_metodologica', 'ComexStat MDIC agregado anual por UF; contexto, não urna; XX = Não Declarada',
    'linhas', v_linhas
  );
END;
$$;

REVOKE ALL ON FUNCTION api.comex(smallint, text, text, boolean, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.comex(smallint, text, text, boolean, integer) TO agente;
