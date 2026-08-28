-- Funções analíticas compostas (Sprint 4) · cruzam Trilha A sem inventar cifra.

CREATE OR REPLACE FUNCTION api.linha_temporal_eleitos(
  p_cargo text,
  p_sg_partido text,
  p_uf text DEFAULT NULL,
  p_anos smallint[] DEFAULT ARRAY[2014, 2018, 2022]::smallint[],
  p_limite integer DEFAULT 500
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_ano smallint;
  v_partes jsonb := '[]'::jsonb;
  v_res jsonb;
  v_total bigint := 0;
  v_siglas text[];
BEGIN
  v_cargo := api._resolver_cargo(p_cargo);
  IF p_sg_partido IS NULL OR btrim(p_sg_partido) = '' THEN
    RETURN jsonb_build_object('status', 'vazio', 'mensagem', 'Informe sg_partido.', 'linhas', '[]'::jsonb);
  END IF;
  v_siglas := api.siglas_equivalentes(p_sg_partido);

  FOREACH v_ano IN ARRAY COALESCE(p_anos, ARRAY[2014, 2018, 2022]::smallint[])
  LOOP
    v_res := api.eleitos(v_ano, p_cargo, p_uf, NULL, false, p_sg_partido, p_limite);
    v_total := v_total + COALESCE(jsonb_array_length(v_res->'linhas'), 0);
    v_partes := v_partes || jsonb_build_array(
      jsonb_build_object(
        'ano', v_ano,
        'status', v_res->'status',
        'n_eleitos', COALESCE(jsonb_array_length(v_res->'linhas'), 0),
        'nota_metodologica', v_res->'nota_metodologica',
        'linhas', COALESCE(v_res->'linhas', '[]'::jsonb)
      )
    );
  END LOOP;

  RETURN jsonb_build_object(
    'status', CASE WHEN v_total > 0 THEN 'ok' ELSE 'vazio' END,
    'nota_metodologica',
      format(
        'Linha temporal de eleitos por ano. Partido=%s equivalentes=%s. Cada bloco usa api.eleitos.',
        upper(btrim(p_sg_partido)),
        array_to_string(COALESCE(v_siglas, ARRAY[upper(btrim(p_sg_partido))]), ',')
      ),
    'series', v_partes
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.cruzamento_social_urna(
  p_ano_urna smallint,
  p_cargo text,
  p_indicador text DEFAULT 'cadunico',
  p_anomes smallint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_top_n integer DEFAULT 15
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, contexto, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_pedido text;
  v_lim integer;
  v_linhas jsonb;
  v_anomes_eff integer;
BEGIN
  v_pedido := format('cruzamento social×urna ano=%s cargo=%s indicador=%s', p_ano_urna, p_cargo, p_indicador);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano_urna, v_cargo, true, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' — informe uf para cruzamento municipal.');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_top_n, 15), 5), 50);
  v_anomes_eff := COALESCE(p_anomes, CASE WHEN p_indicador = 'bolsa_familia' THEN 202608 ELSE 202607 END);

  IF lower(btrim(p_indicador)) = 'bolsa_familia' THEN
    SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.rank_social DESC), '[]'::jsonb)
      INTO v_linhas
    FROM (
      SELECT
        m.cod_ibge,
        m.nome AS nm_municipio,
        m.sg_uf,
        b.qt_familias AS rank_social,
        b.qt_familias,
        v.qt_votos,
        v.nm_urna,
        v.sg_partido
      FROM contexto.bolsa_familia_mun b
      JOIN ref.municipio m ON m.cod_ibge = b.cod_ibge
      LEFT JOIN LATERAL (
        SELECT SUM(vt.qt_votos)::bigint AS qt_votos,
               MAX(vt.nm_urna) AS nm_urna,
               MAX(vt.sg_partido) AS sg_partido
        FROM eleicao.votacao vt
        WHERE vt.ano = p_ano_urna
          AND vt.cd_cargo = v_cargo
          AND vt.cd_municipio_tse = m.cd_municipio_tse
          AND vt.nr_turno = 1
          AND api._eh_eleito(vt.ds_sit_tot_turno)
      ) v ON true
      WHERE b.anomes = v_anomes_eff
        AND api.uf_match(p_uf, m.sg_uf)
      ORDER BY b.qt_familias DESC NULLS LAST
      LIMIT v_lim
    ) t;
  ELSE
    SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.rank_social DESC), '[]'::jsonb)
      INTO v_linhas
    FROM (
      SELECT
        m.cod_ibge,
        m.nome AS nm_municipio,
        m.sg_uf,
        c.qt_familias AS rank_social,
        c.qt_familias,
        v.qt_votos,
        v.nm_urna,
        v.sg_partido
      FROM contexto.cadunico_mun c
      JOIN ref.municipio m ON m.cod_ibge = c.cod_ibge
      LEFT JOIN LATERAL (
        SELECT SUM(vt.qt_votos)::bigint AS qt_votos,
               MAX(vt.nm_urna) AS nm_urna,
               MAX(vt.sg_partido) AS sg_partido
        FROM eleicao.votacao vt
        WHERE vt.ano = p_ano_urna
          AND vt.cd_cargo = v_cargo
          AND vt.cd_municipio_tse = m.cd_municipio_tse
          AND vt.nr_turno = 1
          AND api._eh_eleito(vt.ds_sit_tot_turno)
      ) v ON true
      WHERE c.anomes = v_anomes_eff
        AND api.uf_match(p_uf, m.sg_uf)
      ORDER BY c.qt_familias DESC NULLS LAST
      LIMIT v_lim
    ) t;
  END IF;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'Sem dados sociais ou urna para este cruzamento.',
      'nota_metodologica', 'Indicador social (MDS) × vencedor municipal/estadual na urna. Não é causalidade.',
      'linhas', v_linhas
    );
  END IF;

  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica',
      format(
        'Top municípios por %s (anomes=%s) na UF %s cruzados com eleito na urna %s/%s. Não inferir causalidade.',
        p_indicador, v_anomes_eff, upper(btrim(p_uf)), p_ano_urna, p_cargo
      ),
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.mandato_urna(
  p_ano_eleicao smallint DEFAULT 2022,
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_tema text DEFAULT NULL,
  p_limite integer DEFAULT 30
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, parlamentar, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
  v_tema text;
BEGIN
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 30), 1), 100);
  v_tema := nullif(btrim(COALESCE(p_tema, '')), '');

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.n_proposicoes DESC, t.nm_parlamentar), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      d.id_deputado,
      d.nome AS nm_parlamentar,
      v.sg_uf,
      v.sg_partido,
      dp.metodo AS depara_metodo,
      COUNT(DISTINCT pr.id_proposicao)::int AS n_proposicoes,
      COUNT(DISTINCT vv.id_votacao)::int AS n_votacoes
    FROM parlamentar.deputado d
    LEFT JOIN LATERAL (
      SELECT vv2.sg_uf, vv2.sg_partido
      FROM parlamentar.voto vv2
      WHERE vv2.id_deputado = d.id_deputado
      GROUP BY vv2.sg_uf, vv2.sg_partido
      ORDER BY count(*) DESC
      LIMIT 1
    ) v ON true
    LEFT JOIN parlamentar.depara_tse dp
      ON dp.casa = 'CD'
     AND dp.id_casa = d.id_deputado
     AND dp.ano_eleicao = p_ano_eleicao
    LEFT JOIN parlamentar.proposicao_autor pa ON pa.id_deputado = d.id_deputado
    LEFT JOIN parlamentar.proposicao pr
      ON pr.id_proposicao = pa.id_proposicao
     AND (v_tema IS NULL OR pr.ementa ILIKE '%' || v_tema || '%')
    LEFT JOIN parlamentar.voto vv ON vv.id_deputado = d.id_deputado
    WHERE (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, v.sg_partido))
    GROUP BY d.id_deputado, d.nome, v.sg_uf, v.sg_partido, dp.metodo
    ORDER BY n_proposicoes DESC, d.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'mensagem', 'Sem deputados/proposições neste filtro (Câmara L57).',
      'linhas', '[]'::jsonb
    );
  END IF;

  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica',
      format(
        'Mandato Câmara (L57) cruzado com de-para urna %s. Tema proposição=%s. Atuação ≠ voto eleitoral.',
        p_ano_eleicao, COALESCE(v_tema, '(todos)')
      ),
    'linhas', v_linhas
  );
END;
$$;

GRANT EXECUTE ON FUNCTION api.linha_temporal_eleitos(text, text, text, smallint[], integer) TO agente;
GRANT EXECUTE ON FUNCTION api.cruzamento_social_urna(smallint, text, text, smallint, text, integer) TO agente;
GRANT EXECUTE ON FUNCTION api.mandato_urna(smallint, text, text, text, integer) TO agente;
