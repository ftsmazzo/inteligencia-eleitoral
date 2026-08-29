-- Totais de contas + categorias de despesa + custo/voto.
-- Cifra só Trilha A. Não inventa categoria fora do texto da prestação.

CREATE OR REPLACE FUNCTION api._categoria_despesa(p_texto text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN t ~ 'PROPAGANDA|PUBLICIDADE|MIDIA|FACEBOOK|INSTAGRAM|IMPULSION|GRAFIC|SANTINHO|SANTINH|ADESIVO|BANDEIRA|IMPRESS|JORNAL|TABLOIDE|CARTAO|FOLHETO|OUTDOOR|PANFLET'
      THEN 'publicidade'
    WHEN t ~ 'EVENTO|COMICIO|COMÍCIO|SHOW|PALCO|SOM |ILUMINACAO|ILUMINAÇÃO|BUFFET|COQUETEL'
      THEN 'eventos'
    WHEN t ~ 'ADVOG|JURIDIC|HONORAR|ASSESSORIA JUR'
      THEN 'juridico'
    WHEN t ~ 'CABO ELEITOR|COORDENADOR|PESSOAL|SALARIO|SALÁRIO|ASSESSOR|PRODUTOR|MOTORISTA|ADMINISTR'
      THEN 'pessoal'
    WHEN t ~ 'COMBUST|TRANSP|FRET|VEICULO|VEÍCULO|LOCACAO DE VEIC|LOCAÇÃO DE VEIC|ONIBUS|ÔNIBUS|VAN |MASTER'
      THEN 'logistica'
    WHEN t ~ 'COMITE|COMITÊ|IMOVEL|IMÓVEL|ALUGUEL|LOCACAO DE IM|LOCAÇÃO DE IM|ESPACO PARA COM'
      THEN 'estrutura'
    ELSE 'outros'
  END
  FROM (
    SELECT upper(translate(
      coalesce(p_texto, ''),
      'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
      'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn'
    )) AS t
  ) s;
$$;

CREATE OR REPLACE FUNCTION api.contas_resumo(
  p_ano smallint,
  p_uf text DEFAULT NULL,
  p_cargo text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_sq_candidato bigint DEFAULT NULL,
  p_limite integer DEFAULT 30,
  p_incluir_votos boolean DEFAULT true
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_fora jsonb;
  v_cargo smallint;
  v_cargo_nome text;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('contas_resumo ano=%s', p_ano);
  v_fora := api._checar_ano(p_ano, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_sq_candidato IS NULL AND p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' exige sq_candidato ou uf');
  END IF;
  IF p_cargo IS NOT NULL THEN
    v_cargo := api._resolver_cargo(p_cargo);
    v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido || ' cargo=' || p_cargo);
    IF v_fora IS NOT NULL THEN
      RETURN v_fora;
    END IF;
    SELECT r.nome INTO v_cargo_nome FROM ref.cargo r WHERE r.cd_cargo = v_cargo;
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 30), 1), 100);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.total_despesa DESC NULLS LAST), '[]'::jsonb)
  INTO v_linhas
  FROM (
    WITH base AS (
      SELECT DISTINCT
        d.ano,
        d.sq_candidato,
        max(d.nm_candidato) AS nm_candidato,
        max(d.sg_partido) AS sg_partido,
        max(d.sg_uf) AS sg_uf,
        max(d.ds_cargo) AS ds_cargo,
        max(d.nr_candidato) AS nr_candidato
      FROM eleicao.despesa d
      WHERE d.ano = p_ano
        AND d.sq_candidato IS NOT NULL
        AND (p_sq_candidato IS NULL OR d.sq_candidato = p_sq_candidato)
        AND (p_uf IS NULL OR api.uf_match(p_uf, d.sg_uf))
        AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, d.sg_partido))
        AND (
          v_cargo_nome IS NULL
          OR upper(translate(coalesce(d.ds_cargo, ''), 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
             = upper(translate(v_cargo_nome, 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
        )
      GROUP BY d.ano, d.sq_candidato
    ),
    desp AS (
      SELECT
        d.sq_candidato,
        sum(d.vr_despesa) AS total_despesa,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'publicidade'
        ) AS publicidade,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'eventos'
        ) AS eventos,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'juridico'
        ) AS juridico,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'pessoal'
        ) AS pessoal,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'logistica'
        ) AS logistica,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'estrutura'
        ) AS estrutura,
        sum(d.vr_despesa) FILTER (
          WHERE api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = 'outros'
        ) AS outros
      FROM eleicao.despesa d
      JOIN base b ON b.sq_candidato = d.sq_candidato AND b.ano = d.ano
      WHERE d.ano = p_ano
      GROUP BY d.sq_candidato
    ),
    rec AS (
      SELECT r.sq_candidato, sum(r.vr_receita) AS total_receita
      FROM eleicao.receita r
      JOIN base b ON b.sq_candidato = r.sq_candidato AND b.ano = r.ano
      WHERE r.ano = p_ano
      GROUP BY r.sq_candidato
    ),
    votos AS (
      SELECT v.sq_candidato, sum(v.qt_votos)::bigint AS qt_votos
      FROM eleicao.votacao v
      JOIN base b ON b.sq_candidato = v.sq_candidato AND b.ano = v.ano
      WHERE v.ano = p_ano
        AND (v_cargo IS NULL OR v.cd_cargo = v_cargo)
      GROUP BY v.sq_candidato
    )
    SELECT
      b.ano,
      b.sq_candidato,
      b.nm_candidato,
      b.sg_partido,
      b.sg_uf,
      b.ds_cargo,
      b.nr_candidato,
      round(coalesce(r.total_receita, 0)::numeric, 2) AS total_receita,
      round(coalesce(d.total_despesa, 0)::numeric, 2) AS total_despesa,
      round(coalesce(d.publicidade, 0)::numeric, 2) AS publicidade,
      round(coalesce(d.eventos, 0)::numeric, 2) AS eventos,
      round(coalesce(d.juridico, 0)::numeric, 2) AS juridico,
      round(coalesce(d.pessoal, 0)::numeric, 2) AS pessoal,
      round(coalesce(d.logistica, 0)::numeric, 2) AS logistica,
      round(coalesce(d.estrutura, 0)::numeric, 2) AS estrutura,
      round(coalesce(d.outros, 0)::numeric, 2) AS outros,
      CASE WHEN p_incluir_votos THEN vt.qt_votos ELSE NULL END AS qt_votos,
      CASE
        WHEN p_incluir_votos AND coalesce(vt.qt_votos, 0) > 0
        THEN round((coalesce(d.total_despesa, 0) / vt.qt_votos)::numeric, 4)
        ELSE NULL
      END AS custo_por_voto
    FROM base b
    LEFT JOIN desp d ON d.sq_candidato = b.sq_candidato
    LEFT JOIN rec r ON r.sq_candidato = b.sq_candidato
    LEFT JOIN votos vt ON vt.sq_candidato = b.sq_candidato
    ORDER BY coalesce(d.total_despesa, 0) DESC
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'Dado inexistente neste recorte.',
      'linhas', v_linhas
    );
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica',
      'Totais da prestação TSE. Categorias derivadas do texto (ds_despesa/origem/fornecedor); '
      || 'não é classificação oficial do TSE. custo_por_voto = total_despesa / votos na urna (mesmo ano/sq).',
    'linhas', v_linhas
  );
END;
$$;

-- Despesa com filtro opcional de categoria heurística
DROP FUNCTION IF EXISTS api.despesa(smallint, bigint, text, text, text, integer);
CREATE OR REPLACE FUNCTION api.despesa(
  p_ano smallint,
  p_sq_candidato bigint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_cargo text DEFAULT NULL,
  p_limite integer DEFAULT 200,
  p_categoria text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_fora jsonb;
  v_cargo smallint;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_cargo_nome text;
  v_cat text;
BEGIN
  v_pedido := format('despesa ano=%s', p_ano);
  v_fora := api._checar_ano(p_ano, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_sq_candidato IS NULL AND p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' exige sq_candidato ou uf');
  END IF;
  IF p_cargo IS NOT NULL THEN
    v_cargo := api._resolver_cargo(p_cargo);
    v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido || ' cargo=' || p_cargo);
    IF v_fora IS NOT NULL THEN
      RETURN v_fora;
    END IF;
    SELECT r.nome INTO v_cargo_nome FROM ref.cargo r WHERE r.cd_cargo = v_cargo;
  END IF;
  v_cat := nullif(lower(btrim(coalesce(p_categoria, ''))), '');
  IF v_cat IS NOT NULL AND v_cat NOT IN (
    'publicidade', 'eventos', 'juridico', 'pessoal', 'logistica', 'estrutura', 'outros'
  ) THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'categoria inválida — use publicidade|eventos|juridico|pessoal|logistica|estrutura|outros',
      'linhas', '[]'::jsonb
    );
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      d.ano, d.sq_candidato, d.sg_uf, d.sg_partido, d.nr_candidato, d.ds_cargo, d.nm_candidato,
      d.sq_despesa, d.dt_despesa, d.vr_despesa, d.ds_origem, d.ds_despesa, d.nm_fornecedor,
      api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) AS categoria
    FROM eleicao.despesa d
    WHERE d.ano = p_ano
      AND (p_sq_candidato IS NULL OR d.sq_candidato = p_sq_candidato)
      AND (p_sq_candidato IS NOT NULL OR d.sq_candidato IS NOT NULL)
      AND (p_uf IS NULL OR api.uf_match(p_uf, d.sg_uf))
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, d.sg_partido))
      AND (
        v_cargo_nome IS NULL
        OR upper(translate(coalesce(d.ds_cargo, ''), 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
           = upper(translate(v_cargo_nome, 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
      )
      AND (
        v_cat IS NULL
        OR api._categoria_despesa(coalesce(d.ds_despesa, '') || ' ' || coalesce(d.ds_origem, '') || ' ' || coalesce(d.nm_fornecedor, '')) = v_cat
      )
    ORDER BY d.vr_despesa DESC NULLS LAST, d.dt_despesa DESC NULLS LAST, d.id
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

GRANT EXECUTE ON FUNCTION api._categoria_despesa(text) TO agente;
GRANT EXECUTE ON FUNCTION api.contas_resumo(smallint, text, text, text, bigint, integer, boolean) TO agente;
GRANT EXECUTE ON FUNCTION api.despesa(smallint, bigint, text, text, text, integer, text) TO agente;
