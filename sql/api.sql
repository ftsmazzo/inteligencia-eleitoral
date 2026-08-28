-- Funções nomeadas · Inteligência Eleitoral Brasil
-- SECURITY DEFINER: role agente só EXECUTE em api.

CREATE OR REPLACE FUNCTION api._msg_fora(p_pedido text)
RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT 'Fora do recorte. O escopo da solicitação não faz parte do recorte desta ferramenta, que é: Brasil; cargos de presidente a vereador; eleições federais/estaduais 2014, 2018 e 2022 (resultado) e 2026 (candidatura, resultado após a urna); eleições municipais 2016, 2020 e 2024. Pedido: '
    || COALESCE(NULLIF(btrim(p_pedido), ''), 'não informado')
    || '. Dado inexistente neste recorte.';
$$;

CREATE OR REPLACE FUNCTION api._envelope_fora(p_pedido text)
RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_build_object(
    'status', 'fora_do_recorte',
    'mensagem', api._msg_fora(p_pedido),
    'linhas', '[]'::jsonb
  );
$$;

CREATE OR REPLACE FUNCTION api._resolver_cargo(p_cargo text)
RETURNS smallint
LANGUAGE plpgsql STABLE AS $$
DECLARE
  s text;
  n smallint;
BEGIN
  s := lower(trim(both from coalesce(p_cargo, '')));
  s := replace(s, ' ', '_');
  s := translate(s, 'áàâãéêíóôõúç', 'aaaaeeiooouc');
  IF s ~ '^[0-9]+$' THEN
    RETURN s::smallint;
  END IF;
  RETURN CASE s
    WHEN 'presidente' THEN 1
    WHEN 'pres' THEN 1
    WHEN 'governador' THEN 3
    WHEN 'gov' THEN 3
    WHEN 'senador' THEN 5
    WHEN 'sen' THEN 5
    WHEN 'deputado_federal' THEN 6
    WHEN 'dep_fed' THEN 6
    WHEN 'federal' THEN 6
    WHEN 'deputado_estadual' THEN 7
    WHEN 'dep_est' THEN 7
    WHEN 'estadual' THEN 7
    WHEN 'deputado_distrital' THEN 8
    WHEN 'distrital' THEN 8
    WHEN 'prefeito' THEN 11
    WHEN 'pref' THEN 11
    WHEN 'vereador' THEN 13
    WHEN 'ver' THEN 13
    ELSE NULL
  END;
END;
$$;

CREATE OR REPLACE FUNCTION api._checar_recorte(
  p_ano smallint,
  p_cd_cargo smallint,
  p_precisa_resultado boolean,
  p_pedido text
) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_esfera text;
  v_no boolean;
  v_eleicao ref.eleicao%ROWTYPE;
BEGIN
  IF p_ano IS NULL OR p_cd_cargo IS NULL THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  SELECT c.esfera, c.no_recorte INTO v_esfera, v_no
  FROM ref.cargo c WHERE c.cd_cargo = p_cd_cargo;
  IF NOT FOUND OR v_no IS NOT TRUE THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  IF v_esfera = 'municipal' THEN
    SELECT * INTO v_eleicao FROM ref.eleicao e
    WHERE e.ano = p_ano AND e.esfera = 'municipal';
  ELSE
    SELECT * INTO v_eleicao FROM ref.eleicao e
    WHERE e.ano = p_ano AND e.esfera = 'geral';
  END IF;
  IF NOT FOUND THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  IF p_precisa_resultado AND v_eleicao.tem_resultado IS NOT TRUE THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  RETURN NULL;
END;
$$;

DROP FUNCTION IF EXISTS api.catalogo();

CREATE OR REPLACE FUNCTION api.catalogo()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
  SELECT jsonb_build_object(
    'status', 'ok',
    'recorte', 'Brasil; Pres a Ver; gerais 2014/2018/2022 + 2026 viva; municipais 2016/2020/2024',
    'pacotes', jsonb_build_array(
      jsonb_build_object('pacote','catalogo','nota','este objeto'),
      jsonb_build_object('pacote','nominata','anos','2014–2026','nota','2026 sem resultado de urna'),
      jsonb_build_object('pacote','votacao','anos','2014,2016,2018,2020,2022,2024','nota','exige ano+cargo e (uf ou cod_ibge ou nacional=true)'),
      jsonb_build_object('pacote','comparecimento','anos','2014,2016,2018,2020,2022,2024','nota','detalhe da apuração'),
      jsonb_build_object('pacote','eleitorado','anos','2014–2026','nota','perfil; 2026 é cadastro, não urna'),
      jsonb_build_object('pacote','coligacao','anos','2014,2016,2018,2020,2022,2024,2026','nota','2014/2016 municipal: coligação proporcional; 2018+ federação'),
      jsonb_build_object('pacote','vagas','anos','2014,2016,2018,2020,2022,2024,2026','nota','cadeiras por cargo×UF (geral) ou cargo×município (municipal)'),
      jsonb_build_object('pacote','bem','anos','2014–2026','nota','exige ano+sq_candidato; bens declarados no TSE'),
      jsonb_build_object('pacote','receita','anos','2014–2026','nota','prestação; exige ano e (sq_candidato ou uf); sem CPF'),
      jsonb_build_object('pacote','despesa','anos','2014–2026','nota','prestação contratada/declarada; exige ano e (sq_candidato ou uf); sem CPF'),
      jsonb_build_object('pacote','eleitos','anos','2014,2016,2018,2020,2022,2024','nota','mapa político; deriva de votacao.ds_sit_tot_turno; exige ano+cargo e (uf ou cod_ibge ou nacional); 2026 fora até haver urna'),
      jsonb_build_object('pacote','populacao','anos','2010,2014,2016,2018,2020,2021,2022,2024,2025','nota','IBGE; censo 2010/2022 e estimativas SIDRA 6579; 2023/2026 sem publicação própria; exige ano+(uf|cod_ibge|nacional)'),
      jsonb_build_object('pacote','cadunico','anomes','202607','nota','Cadastro Único municipal MDS; snapshot; exige anomes opcional+(uf|cod_ibge|nacional)'),
      jsonb_build_object('pacote','bolsa_familia','anomes','202608','nota','Bolsa Família municipal; snapshot de repasse; exige anomes opcional+(uf|cod_ibge|nacional)'),
      jsonb_build_object('pacote','deputados_casa','nota','cadastro Câmara; filtro uf/partido/nome; legislatura via de-para/votos'),
      jsonb_build_object('pacote','senadores','nota','cadastro Senado L56/L57/atual'),
      jsonb_build_object('pacote','proposicoes','anos','2023–2026','nota','proposições Câmara; exige ano; autor opcional'),
      jsonb_build_object('pacote','votos_camara','anos','2023–2026','nota','votos nominais Câmara; exige id_deputado ou uf'),
      jsonb_build_object('pacote','depara_parlamentar','nota','vínculo Casa↔TSE 2022 (uf+nome); confianca declarada'),
      jsonb_build_object('pacote','acervo','nota','Trilha B: planos/programas/notas com vigência; cifra no texto é pista'),
      jsonb_build_object('pacote','clima','nota','Radar: consulta livre q/canal/tipo/janela_horas; nivel=indicio; campaign_id opcional')
    )
  );
$$;

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
  v_fora jsonb;
  v_tse integer;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('nominata ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
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
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.votacao(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_turno smallint DEFAULT 1,
  p_sg_partido text DEFAULT NULL,
  p_sq_candidato bigint DEFAULT NULL,
  p_nr_candidato integer DEFAULT NULL,
  p_nm_urna text DEFAULT NULL,
  p_base_pct text DEFAULT NULL,
  p_limite integer DEFAULT 100
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_tse integer;
  v_lim integer;
  v_den numeric;
  v_soma numeric;
  v_base text;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('votacao ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, true, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE
     AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' sem uf/cod_ibge/nacional');
  END IF;
  v_base := NULLIF(lower(btrim(p_base_pct)), '');
  IF v_base IS NOT NULL AND v_base NOT IN ('validos', 'soma_dois') THEN
    RETURN api._envelope_fora(v_pedido || ' base_pct inválida');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 100), 1), 500);
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
  END IF;

  SELECT COALESCE(SUM(d.qt_votos_nominais), 0) + COALESCE(SUM(d.qt_votos_legenda), 0)
    INTO v_den
  FROM eleicao.detalhe_munzona d
  WHERE d.ano = p_ano
    AND d.cd_cargo = v_cargo
    AND d.nr_turno = COALESCE(p_turno, 1)
    AND (p_uf IS NULL OR api.uf_match(p_uf, d.sg_uf))
    AND (v_tse IS NULL OR d.cd_municipio_tse = v_tse);

  WITH agg AS (
    SELECT
      v.sq_candidato,
      MAX(v.nr_candidato) AS nr_candidato,
      MAX(v.nm_urna) AS nm_urna,
      MAX(v.sg_partido) AS sg_partido,
      MAX(v.ds_sit_tot_turno) AS ds_sit_tot_turno,
      SUM(v.qt_votos)::bigint AS qt_votos
    FROM eleicao.votacao v
    WHERE v.ano = p_ano
      AND v.cd_cargo = v_cargo
      AND v.nr_turno = COALESCE(p_turno, 1)
      AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
      AND (v_tse IS NULL OR v.cd_municipio_tse = v_tse)
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, v.sg_partido))
      AND (p_sq_candidato IS NULL OR v.sq_candidato = p_sq_candidato)
      AND (p_nr_candidato IS NULL OR v.nr_candidato = p_nr_candidato)
      AND (p_nm_urna IS NULL OR v.nm_urna ILIKE '%' || p_nm_urna || '%')
    GROUP BY v.sq_candidato
  )
  SELECT COALESCE(SUM(qt_votos), 0) INTO v_soma FROM agg;

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.qt_votos DESC), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      a.sq_candidato, a.nr_candidato, a.nm_urna, a.sg_partido, a.ds_sit_tot_turno, a.qt_votos,
      CASE WHEN v_base = 'validos' AND v_den > 0
           THEN round((a.qt_votos::numeric / v_den) * 100, 4) END AS pct,
      CASE WHEN v_base = 'soma_dois' AND v_soma > 0
           THEN round((a.qt_votos::numeric / v_soma) * 100, 4) END AS pct_conjunto
    FROM (
      SELECT * FROM (
        SELECT
          v.sq_candidato,
          MAX(v.nr_candidato) AS nr_candidato,
          MAX(v.nm_urna) AS nm_urna,
          MAX(v.sg_partido) AS sg_partido,
          MAX(v.ds_sit_tot_turno) AS ds_sit_tot_turno,
          SUM(v.qt_votos)::bigint AS qt_votos
        FROM eleicao.votacao v
        WHERE v.ano = p_ano
          AND v.cd_cargo = v_cargo
          AND v.nr_turno = COALESCE(p_turno, 1)
          AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
          AND (v_tse IS NULL OR v.cd_municipio_tse = v_tse)
          AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, v.sg_partido))
          AND (p_sq_candidato IS NULL OR v.sq_candidato = p_sq_candidato)
          AND (p_nr_candidato IS NULL OR v.nr_candidato = p_nr_candidato)
          AND (p_nm_urna IS NULL OR v.nm_urna ILIKE '%' || p_nm_urna || '%')
        GROUP BY v.sq_candidato
      ) x
      ORDER BY qt_votos DESC
      LIMIT v_lim
    ) a
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'base_pct', v_base,
    'denominador_validos', CASE WHEN v_base = 'validos' THEN v_den END,
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.comparecimento(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_turno smallint DEFAULT 1
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_tse integer;
  v_pedido text;
  v_row record;
BEGIN
  v_pedido := format('comparecimento ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, true, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE
     AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' sem uf/cod_ibge/nacional');
  END IF;
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
  END IF;
  SELECT
    SUM(d.qt_aptos) AS qt_aptos,
    SUM(d.qt_comparecimento) AS qt_comparecimento,
    SUM(d.qt_abstencoes) AS qt_abstencoes,
    SUM(d.qt_votos_brancos) AS qt_votos_brancos,
    SUM(d.qt_votos_nulos) AS qt_votos_nulos,
    SUM(d.qt_votos_nominais) AS qt_votos_nominais,
    SUM(d.qt_votos_legenda) AS qt_votos_legenda
  INTO v_row
  FROM eleicao.detalhe_munzona d
  WHERE d.ano = p_ano
    AND d.cd_cargo = v_cargo
    AND d.nr_turno = COALESCE(p_turno, 1)
    AND (p_uf IS NULL OR api.uf_match(p_uf, d.sg_uf))
    AND (v_tse IS NULL OR d.cd_municipio_tse = v_tse);
  IF v_row.qt_aptos IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'linhas', jsonb_build_array(to_jsonb(v_row))
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.eleitorado(
  p_ano smallint,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_tse integer;
  v_total bigint;
BEGIN
  IF p_ano NOT IN (2014, 2016, 2018, 2020, 2022, 2024, 2026) THEN
    RETURN api._envelope_fora('eleitorado ano=' || coalesce(p_ano::text, ''));
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE
     AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
    RETURN api._envelope_fora('eleitorado sem uf/cod_ibge/nacional');
  END IF;
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
  END IF;
  SELECT SUM(e.qt_eleitores) INTO v_total
  FROM eleicao.eleitorado e
  WHERE e.ano = p_ano
    AND (p_uf IS NULL OR api.uf_match(p_uf, e.sg_uf))
    AND (v_tse IS NULL OR e.cd_municipio_tse = v_tse);
  IF v_total IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'ano', p_ano,
    'nota_2026', CASE WHEN p_ano = 2026 THEN 'cadastro, não resultado de urna' END,
    'qt_eleitores', v_total
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.coligacao(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_sq_coligacao bigint DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_tse integer;
  v_mun integer;
  v_filtra_mun boolean := false;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_nota text;
BEGIN
  v_pedido := format('coligacao ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
    v_mun := v_tse;
    v_filtra_mun := true;
  ELSIF v_cargo IN (11, 12, 13) AND p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' municipal exige uf ou cod_ibge');
  ELSIF v_cargo NOT IN (11, 12, 13) THEN
    v_mun := 0;
    v_filtra_mun := true;
  END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      c.ano, c.cd_cargo, r.nome AS cargo, c.sg_uf, c.cd_municipio_tse,
      c.sq_coligacao, c.nm_coligacao, c.ds_composicao, c.sg_partido
    FROM eleicao.coligacao c
    JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
    WHERE c.ano = p_ano
      AND c.cd_cargo = v_cargo
      AND (p_uf IS NULL OR api.uf_match(p_uf, c.sg_uf))
      AND (NOT v_filtra_mun OR c.cd_municipio_tse = v_mun)
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, c.sg_partido))
      AND (p_sq_coligacao IS NULL OR c.sq_coligacao = p_sq_coligacao)
    ORDER BY c.sg_uf, c.cd_municipio_tse, c.nm_coligacao, c.sg_partido
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  v_nota := CASE
    WHEN p_ano = 2014 THEN 'coligação proporcional (regra pré-2018)'
    WHEN p_ano = 2016 AND v_cargo = 13 THEN 'coligação proporcional municipal'
    WHEN p_ano >= 2018 THEN 'sem coligação proporcional em dep.; federação/partido'
    ELSE NULL
  END;
  RETURN jsonb_build_object('status','ok','nota_metodologica', v_nota, 'linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.vagas(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_tse integer;
  v_mun integer;
  v_filtra_mun boolean := false;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
BEGIN
  v_pedido := format('vagas ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, false, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
    v_mun := v_tse;
    v_filtra_mun := true;
  ELSIF v_cargo IN (11, 12, 13) AND p_uf IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' municipal exige uf ou cod_ibge');
  ELSIF v_cargo NOT IN (11, 12, 13) THEN
    v_mun := 0;
    v_filtra_mun := true;
  END IF;
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      v.ano, v.cd_cargo, r.nome AS cargo, v.sg_uf, v.cd_municipio_tse, v.qt_vagas
    FROM eleicao.vagas v
    JOIN ref.cargo r ON r.cd_cargo = v.cd_cargo
    WHERE v.ano = p_ano
      AND v.cd_cargo = v_cargo
      AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
      AND (NOT v_filtra_mun OR v.cd_municipio_tse = v_mun)
    ORDER BY v.sg_uf, v.cd_municipio_tse
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api._checar_ano(p_ano smallint, p_pedido text)
RETURNS jsonb
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF p_ano IS NULL THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM ref.eleicao e WHERE e.ano = p_ano) THEN
    RETURN api._envelope_fora(p_pedido);
  END IF;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION api.bem(
  p_ano smallint,
  p_sq_candidato bigint,
  p_limite integer DEFAULT 200
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
  v_pedido := format('bem ano=%s sq=%s', p_ano, p_sq_candidato);
  v_fora := api._checar_ano(p_ano, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF p_sq_candidato IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' exige sq_candidato');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      b.ano, b.sq_candidato, b.nr_ordem, b.cd_tipo_bem, b.ds_tipo_bem, b.ds_bem, b.vr_bem
    FROM eleicao.bem b
    WHERE b.ano = p_ano
      AND b.sq_candidato = p_sq_candidato
    ORDER BY b.nr_ordem
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.receita(
  p_ano smallint,
  p_sq_candidato bigint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_cargo text DEFAULT NULL,
  p_limite integer DEFAULT 200
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
BEGIN
  v_pedido := format('receita ano=%s', p_ano);
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
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      r.ano, r.sq_candidato, r.sg_uf, r.sg_partido, r.nr_candidato, r.ds_cargo, r.nm_candidato,
      r.sq_receita, r.dt_receita, r.vr_receita, r.ds_fonte, r.ds_origem, r.ds_especie,
      r.ds_receita, r.nm_doador, r.sg_partido_doador
    FROM eleicao.receita r
    WHERE r.ano = p_ano
      AND (p_sq_candidato IS NULL OR r.sq_candidato = p_sq_candidato)
      AND (p_sq_candidato IS NOT NULL OR r.sq_candidato IS NOT NULL)
      AND (p_uf IS NULL OR api.uf_match(p_uf, r.sg_uf))
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, r.sg_partido))
      AND (
        v_cargo_nome IS NULL
        OR upper(translate(coalesce(r.ds_cargo, ''), 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
           = upper(translate(v_cargo_nome, 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
      )
    ORDER BY r.vr_receita DESC NULLS LAST, r.dt_receita DESC NULLS LAST, r.id
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.despesa(
  p_ano smallint,
  p_sq_candidato bigint DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_cargo text DEFAULT NULL,
  p_limite integer DEFAULT 200
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
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      d.ano, d.sq_candidato, d.sg_uf, d.sg_partido, d.nr_candidato, d.ds_cargo, d.nm_candidato,
      d.sq_despesa, d.dt_despesa, d.vr_despesa, d.ds_origem, d.ds_despesa, d.nm_fornecedor
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
    ORDER BY d.vr_despesa DESC NULLS LAST, d.dt_despesa DESC NULLS LAST, d.id
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api._eh_eleito(p_sit text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT p_sit IS NOT NULL
    AND (
      p_sit = 'ELEITO'
      OR p_sit = 'ELEITO POR QP'
      OR p_sit ~* '^ELEITO POR M'
    );
$$;

CREATE OR REPLACE FUNCTION api.eleitos(
  p_ano smallint,
  p_cargo text,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_sg_partido text DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, eleicao, pg_temp
AS $$
DECLARE
  v_cargo smallint;
  v_fora jsonb;
  v_tse integer;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_siglas text[];
  v_nota text;
BEGIN
  v_pedido := format('eleitos ano=%s cargo=%s', p_ano, p_cargo);
  v_cargo := api._resolver_cargo(p_cargo);
  v_fora := api._checar_recorte(p_ano, v_cargo, true, v_pedido);
  IF v_fora IS NOT NULL THEN
    RETURN v_fora;
  END IF;
  IF COALESCE(p_nacional, false) IS NOT TRUE
     AND p_uf IS NULL AND p_cod_ibge IS NULL THEN
    RETURN api._envelope_fora(v_pedido || ' sem uf/cod_ibge/nacional');
  END IF;
  IF v_cargo IN (11, 12, 13) AND COALESCE(p_nacional, false) IS TRUE THEN
    RETURN api._envelope_fora(v_pedido || ' municipal não admite nacional');
  END IF;
  IF api.eh_regiao(p_uf) THEN
    v_lim := LEAST(GREATEST(COALESCE(p_limite, 500), 1), 500);
  ELSE
    v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  END IF;
  v_siglas := api.siglas_equivalentes(p_sg_partido);
  v_nota := 'eleito = ds_sit_tot_turno ELEITO / ELEITO POR QP / ELEITO POR MÉDIA; não é lista cadastral à parte';
  IF p_sg_partido IS NOT NULL AND v_siglas IS NOT NULL AND array_length(v_siglas, 1) > 1 THEN
    v_nota := v_nota || format(
      ' | filtro partido expandido: pedido=%s equivalentes=%s (sigla na urna pode mudar no tempo; ver ref.partido_linha)',
      upper(btrim(p_sg_partido)),
      array_to_string(v_siglas, ',')
    );
  END IF;
  IF api.eh_regiao(p_uf) THEN
    v_nota := v_nota || format(' | região %s = UFs %s', upper(btrim(p_uf)), array_to_string(api.ufs_da_regiao(p_uf), ','));
  END IF;
  IF p_cod_ibge IS NOT NULL THEN
    SELECT m.cd_municipio_tse INTO v_tse FROM ref.municipio m WHERE m.cod_ibge = p_cod_ibge;
    IF v_tse IS NULL THEN
      RETURN jsonb_build_object('status','vazio','mensagem','Município inexistente neste recorte.','linhas','[]'::jsonb);
    END IF;
  END IF;

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.qt_votos DESC NULLS LAST, t.nm_urna), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      p_ano AS ano,
      v_cargo AS cd_cargo,
      r.nome AS cargo,
      e.sg_uf,
      e.cd_municipio_tse,
      m.cod_ibge,
      m.nome AS nm_municipio,
      e.sq_candidato,
      e.nr_candidato,
      e.nm_urna,
      e.nm_candidato,
      e.sg_partido,
      e.nr_turno,
      e.ds_sit_tot_turno,
      e.qt_votos
    FROM (
      SELECT DISTINCT ON (a.sq_candidato)
        a.sq_candidato,
        a.nr_turno,
        a.nr_candidato,
        a.nm_urna,
        a.sg_partido,
        a.ds_sit_tot_turno,
        a.sg_uf,
        a.qt_votos,
        c.nm_candidato,
        CASE WHEN v_cargo IN (11, 12, 13) THEN c.cd_municipio_tse END AS cd_municipio_tse
      FROM (
        SELECT
          v.sq_candidato,
          v.nr_turno,
          MAX(v.nr_candidato) AS nr_candidato,
          MAX(v.nm_urna) AS nm_urna,
          MAX(v.sg_partido) AS sg_partido,
          MAX(v.ds_sit_tot_turno) AS ds_sit_tot_turno,
          MAX(v.sg_uf) AS sg_uf,
          SUM(v.qt_votos)::bigint AS qt_votos
        FROM eleicao.votacao v
        WHERE v.ano = p_ano
          AND v.cd_cargo = v_cargo
          AND api._eh_eleito(v.ds_sit_tot_turno)
          AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
          AND (v_tse IS NULL OR v.cd_municipio_tse = v_tse)
          AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, v.sg_partido))
        GROUP BY v.sq_candidato, v.nr_turno
      ) a
      LEFT JOIN eleicao.candidatura c
        ON c.ano = p_ano AND c.sq_candidato = a.sq_candidato
      ORDER BY a.sq_candidato, a.nr_turno DESC
    ) e
    JOIN ref.cargo r ON r.cd_cargo = v_cargo
    LEFT JOIN ref.municipio m ON m.cd_municipio_tse = e.cd_municipio_tse
    ORDER BY e.qt_votos DESC NULLS LAST, e.nm_urna
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status','vazio',
      'mensagem','Zero eleitos neste recorte (filtro aplicado; base existe).',
      'nota_metodologica', v_nota,
      'linhas', v_linhas
    );
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica', v_nota,
    'siglas_equivalentes', to_jsonb(COALESCE(v_siglas, ARRAY[]::text[])),
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.populacao(
  p_ano smallint,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, contexto, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_total bigint;
  v_fonte text;
  v_anos_ok smallint[] := ARRAY[2010, 2014, 2016, 2018, 2020, 2021, 2022, 2024, 2025];
BEGIN
  v_pedido := format('populacao ano=%s', p_ano);
  IF p_ano IS NULL OR p_ano <> ALL (v_anos_ok) THEN
    RETURN api._envelope_fora(
      v_pedido || ' (IBGE: censo 2010/2022; estimativas 2014/2016/2018/2020/2021/2024/2025; sem 2023/2026 inventado)'
    );
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

  SELECT COALESCE(SUM(p.qt_populacao), 0), MAX(p.ds_fonte)
    INTO v_total, v_fonte
  FROM contexto.populacao_mun p
  JOIN ref.municipio m ON m.cod_ibge = p.cod_ibge
  WHERE p.ano = p_ano
    AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
    AND (p_cod_ibge IS NULL OR p.cod_ibge = p_cod_ibge);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.qt_populacao DESC, t.nome), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      p.ano, p.cod_ibge, m.nome, m.sg_uf, p.qt_populacao, p.ds_fonte
    FROM contexto.populacao_mun p
    JOIN ref.municipio m ON m.cod_ibge = p.cod_ibge
    WHERE p.ano = p_ano
      AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
      AND (p_cod_ibge IS NULL OR p.cod_ibge = p_cod_ibge)
    ORDER BY p.qt_populacao DESC, m.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'ano', p_ano,
    'ds_fonte', v_fonte,
    'qt_populacao_total', v_total,
    'nota_metodologica', CASE
      WHEN p_ano IN (2010, 2022) THEN 'Censo Demográfico IBGE'
      ELSE 'Estimativa populacional IBGE (SIDRA 6579), referência 1º julho'
    END,
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.cadunico(
  p_anomes integer DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, contexto, pg_temp
AS $$
DECLARE
  v_anomes integer;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_total_fam bigint;
BEGIN
  v_pedido := format('cadunico anomes=%s', p_anomes);
  SELECT COALESCE(p_anomes, MAX(c.anomes)) INTO v_anomes FROM contexto.cadunico_mun c;
  IF v_anomes IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF p_anomes IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM contexto.cadunico_mun c WHERE c.anomes = p_anomes
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

  SELECT COALESCE(SUM(c.qt_familias), 0) INTO v_total_fam
  FROM contexto.cadunico_mun c
  JOIN ref.municipio m ON m.cod_ibge = c.cod_ibge
  WHERE c.anomes = v_anomes
    AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
    AND (p_cod_ibge IS NULL OR c.cod_ibge = p_cod_ibge);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.qt_familias DESC NULLS LAST, t.nome), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      c.anomes, c.cod_ibge, m.nome, m.sg_uf,
      c.qt_familias, c.qt_familias_ate_meio_sm, c.qt_familias_acima_meio_sm,
      c.qt_familias_pobreza_pbf, c.qt_familias_baixa_renda, c.qt_familias_extrema_pobreza,
      c.qt_pessoas_ate_meio_sm, c.qt_pessoas_acima_meio_sm, c.taxa_atualizacao_ate_meio_sm
    FROM contexto.cadunico_mun c
    JOIN ref.municipio m ON m.cod_ibge = c.cod_ibge
    WHERE c.anomes = v_anomes
      AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
      AND (p_cod_ibge IS NULL OR c.cod_ibge = p_cod_ibge)
    ORDER BY c.qt_familias DESC NULLS LAST, m.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'anomes', v_anomes,
    'qt_familias_total', v_total_fam,
    'nota_metodologica', 'Cadastro Único municipal (MDS); snapshot por competência anomes; não é série histórica nesta carga',
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.bolsa_familia(
  p_anomes integer DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_cod_ibge integer DEFAULT NULL,
  p_nacional boolean DEFAULT false,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, contexto, pg_temp
AS $$
DECLARE
  v_anomes integer;
  v_lim integer;
  v_linhas jsonb;
  v_pedido text;
  v_total_fam bigint;
  v_total_vr numeric;
BEGIN
  v_pedido := format('bolsa_familia anomes=%s', p_anomes);
  SELECT COALESCE(p_anomes, MAX(b.anomes)) INTO v_anomes FROM contexto.bolsa_familia_mun b;
  IF v_anomes IS NULL THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas','[]'::jsonb);
  END IF;
  IF p_anomes IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM contexto.bolsa_familia_mun b WHERE b.anomes = p_anomes
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

  SELECT COALESCE(SUM(b.qt_familias), 0), COALESCE(SUM(b.vr_repassado), 0)
    INTO v_total_fam, v_total_vr
  FROM contexto.bolsa_familia_mun b
  JOIN ref.municipio m ON m.cod_ibge = b.cod_ibge
  WHERE b.anomes = v_anomes
    AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
    AND (p_cod_ibge IS NULL OR b.cod_ibge = p_cod_ibge);

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.vr_repassado DESC NULLS LAST, t.nome), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      b.anomes, b.cod_ibge, m.nome, m.sg_uf,
      b.qt_familias, b.qt_pessoas, b.vr_repassado, b.vr_medio_beneficio, b.pct_familias_rf_mulher
    FROM contexto.bolsa_familia_mun b
    JOIN ref.municipio m ON m.cod_ibge = b.cod_ibge
    WHERE b.anomes = v_anomes
      AND (p_uf IS NULL OR api.uf_match(p_uf, m.sg_uf))
      AND (p_cod_ibge IS NULL OR b.cod_ibge = p_cod_ibge)
    ORDER BY b.vr_repassado DESC NULLS LAST, m.nome
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'anomes', v_anomes,
    'qt_familias_total', v_total_fam,
    'vr_repassado_total', v_total_vr,
    'nota_metodologica', 'Bolsa Família municipal (repasse); snapshot por competência anomes; não é série histórica nesta carga',
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.deputados_casa(
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_nome text DEFAULT NULL,
  p_id_deputado integer DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, parlamentar, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
BEGIN
  IF p_uf IS NULL AND p_sg_partido IS NULL AND p_nome IS NULL AND p_id_deputado IS NULL THEN
    RETURN api._envelope_fora('deputados_casa exige uf, partido, nome ou id_deputado');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT DISTINCT ON (d.id_deputado)
      d.id_deputado, d.nome, d.nome_civil, d.sigla_sexo,
      d.id_legislatura_ini, d.id_legislatura_fim, d.uri,
      v.sg_uf, v.sg_partido, dp.sq_candidato
    FROM parlamentar.deputado d
    LEFT JOIN LATERAL (
      SELECT vv.sg_uf, vv.sg_partido
      FROM parlamentar.voto vv
      WHERE vv.id_deputado = d.id_deputado
      GROUP BY vv.sg_uf, vv.sg_partido
      ORDER BY count(*) DESC
      LIMIT 1
    ) v ON true
    LEFT JOIN parlamentar.depara_tse dp
      ON dp.casa = 'CD' AND dp.id_casa = d.id_deputado AND dp.ano_eleicao = 2022
    WHERE (p_id_deputado IS NULL OR d.id_deputado = p_id_deputado)
      AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, v.sg_partido))
      AND (
        p_nome IS NULL
        OR d.nome ILIKE '%' || p_nome || '%'
        OR d.nome_civil ILIKE '%' || p_nome || '%'
      )
    ORDER BY d.id_deputado, d.nome
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.senadores(
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_nome text DEFAULT NULL,
  p_id_senador integer DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, parlamentar, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
BEGIN
  IF p_uf IS NULL AND p_sg_partido IS NULL AND p_nome IS NULL AND p_id_senador IS NULL THEN
    RETURN api._envelope_fora('senadores exige uf, partido, nome ou id_senador');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      s.id_senador, s.nome_parlamentar, s.nome_completo, s.sg_partido, s.sg_uf,
      s.id_legislatura, s.em_exercicio, s.uri, dp.sq_candidato
    FROM parlamentar.senador s
    LEFT JOIN parlamentar.depara_tse dp
      ON dp.casa = 'SF' AND dp.id_casa = s.id_senador AND dp.ano_eleicao = 2022
    WHERE (p_id_senador IS NULL OR s.id_senador = p_id_senador)
      AND (p_uf IS NULL OR api.uf_match(p_uf, s.sg_uf))
      AND (p_sg_partido IS NULL OR api.partido_match(p_sg_partido, s.sg_partido))
      AND (
        p_nome IS NULL
        OR s.nome_parlamentar ILIKE '%' || p_nome || '%'
        OR s.nome_completo ILIKE '%' || p_nome || '%'
      )
    ORDER BY s.sg_uf, s.nome_parlamentar
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.proposicoes(
  p_ano smallint,
  p_sigla_tipo text DEFAULT NULL,
  p_id_deputado integer DEFAULT NULL,
  p_limite integer DEFAULT 100
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, parlamentar, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
BEGIN
  IF p_ano IS NULL OR p_ano NOT IN (2023, 2024, 2025, 2026) THEN
    RETURN api._envelope_fora('proposicoes ano=' || coalesce(p_ano::text,'') || ' (MVP 2023–2026 Câmara)');
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 100), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      p.id_proposicao, p.sigla_tipo, p.numero, p.ano, p.ementa,
      p.data_apresentacao, p.descricao_situacao, p.uri
    FROM parlamentar.proposicao p
    WHERE p.ano = p_ano
      AND (p_sigla_tipo IS NULL OR p.sigla_tipo = upper(p_sigla_tipo))
      AND (
        p_id_deputado IS NULL
        OR EXISTS (
          SELECT 1 FROM parlamentar.proposicao_autor a
          WHERE a.id_proposicao = p.id_proposicao AND a.id_deputado = p_id_deputado
        )
      )
    ORDER BY p.data_apresentacao DESC NULLS LAST, p.id_proposicao DESC
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica', 'Proposições Câmara dos Deputados; Senado matérias ainda não espelhadas em lote',
    'linhas', v_linhas
  );
END;
$$;

CREATE OR REPLACE FUNCTION api.votos_camara(
  p_ano smallint DEFAULT NULL,
  p_id_deputado integer DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_limite integer DEFAULT 100
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, parlamentar, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
BEGIN
  IF p_id_deputado IS NULL AND p_uf IS NULL THEN
    RETURN api._envelope_fora('votos_camara exige id_deputado ou uf');
  END IF;
  IF p_ano IS NOT NULL AND p_ano NOT IN (2023, 2024, 2025, 2026) THEN
    RETURN api._envelope_fora('votos_camara ano=' || p_ano::text);
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 100), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      vt.ano, v.id_votacao, vt.data_votacao, vt.descricao, vt.aprovacao,
      v.id_deputado, v.voto, v.sg_partido, v.sg_uf
    FROM parlamentar.voto v
    JOIN parlamentar.votacao vt ON vt.id_votacao = v.id_votacao
    WHERE (p_id_deputado IS NULL OR v.id_deputado = p_id_deputado)
      AND (p_uf IS NULL OR api.uf_match(p_uf, v.sg_uf))
      AND (p_ano IS NULL OR vt.ano = p_ano)
    ORDER BY vt.data_votacao DESC NULLS LAST, v.id_votacao
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object('status','ok','linhas', v_linhas);
END;
$$;

CREATE OR REPLACE FUNCTION api.depara_parlamentar(
  p_casa text DEFAULT NULL,
  p_ano_eleicao smallint DEFAULT 2022,
  p_uf text DEFAULT NULL,
  p_limite integer DEFAULT 200
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, ref, parlamentar, eleicao, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
BEGIN
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 200), 1), 500);
  SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb) INTO v_linhas
  FROM (
    SELECT
      dp.casa, dp.id_casa, dp.ano_eleicao, dp.sq_candidato, dp.metodo, dp.confianca,
      COALESCE(d.nome, s.nome_parlamentar) AS nome_casa,
      c.nm_urna, c.sg_partido, c.sg_uf
    FROM parlamentar.depara_tse dp
    LEFT JOIN parlamentar.deputado d ON dp.casa = 'CD' AND d.id_deputado = dp.id_casa
    LEFT JOIN parlamentar.senador s ON dp.casa = 'SF' AND s.id_senador = dp.id_casa
    LEFT JOIN eleicao.candidatura c
      ON c.ano = dp.ano_eleicao AND c.sq_candidato = dp.sq_candidato
    WHERE (p_casa IS NULL OR dp.casa = upper(p_casa))
      AND dp.ano_eleicao = COALESCE(p_ano_eleicao, 2022)
      AND (p_uf IS NULL OR api.uf_match(p_uf, c.sg_uf) OR api.uf_match(p_uf, s.sg_uf))
    ORDER BY dp.casa, c.sg_uf, COALESCE(d.nome, s.nome_parlamentar)
    LIMIT v_lim
  ) t;
  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object('status','vazio','mensagem','Dado inexistente neste recorte.','linhas', v_linhas);
  END IF;
  RETURN jsonb_build_object(
    'status', 'ok',
    'nota_metodologica', 'De-para automático uf+nome_norm sobre eleitos 2022; confianca 0.80; revisar casos ambíguos',
    'linhas', v_linhas
  );
END;
$$;

REVOKE ALL ON FUNCTION api.catalogo() FROM PUBLIC;
REVOKE ALL ON FUNCTION api.nominata(smallint, text, text, integer, text, bigint, integer, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.votacao(smallint, text, text, integer, boolean, smallint, text, bigint, integer, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.comparecimento(smallint, text, text, integer, boolean, smallint) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.eleitorado(smallint, text, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.coligacao(smallint, text, text, integer, text, bigint, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.vagas(smallint, text, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.bem(smallint, bigint, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.receita(smallint, bigint, text, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.despesa(smallint, bigint, text, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.eleitos(smallint, text, text, integer, boolean, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.populacao(smallint, text, integer, boolean, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.cadunico(integer, text, integer, boolean, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.bolsa_familia(integer, text, integer, boolean, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.deputados_casa(text, text, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.senadores(text, text, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.proposicoes(smallint, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.votos_camara(smallint, integer, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.depara_parlamentar(text, smallint, text, integer) FROM PUBLIC;
