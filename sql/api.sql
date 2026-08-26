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
      jsonb_build_object('pacote','vagas','anos','2014,2016,2018,2020,2022,2024,2026','nota','cadeiras por cargo×UF (geral) ou cargo×município (municipal)')
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
      AND (p_uf IS NULL OR c.sg_uf = upper(p_uf))
      AND (v_tse IS NULL OR c.cd_municipio_tse = v_tse)
      AND (p_sg_partido IS NULL OR c.sg_partido = p_sg_partido)
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
    AND (p_uf IS NULL OR d.sg_uf = upper(p_uf))
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
      AND (p_uf IS NULL OR v.sg_uf = upper(p_uf))
      AND (v_tse IS NULL OR v.cd_municipio_tse = v_tse)
      AND (p_sg_partido IS NULL OR v.sg_partido = p_sg_partido)
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
          AND (p_uf IS NULL OR v.sg_uf = upper(p_uf))
          AND (v_tse IS NULL OR v.cd_municipio_tse = v_tse)
          AND (p_sg_partido IS NULL OR v.sg_partido = p_sg_partido)
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
    AND (p_uf IS NULL OR d.sg_uf = upper(p_uf))
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
    AND (p_uf IS NULL OR e.sg_uf = upper(p_uf))
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
      AND (p_uf IS NULL OR c.sg_uf = upper(p_uf))
      AND (NOT v_filtra_mun OR c.cd_municipio_tse = v_mun)
      AND (p_sg_partido IS NULL OR c.sg_partido = p_sg_partido)
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
      AND (p_uf IS NULL OR v.sg_uf = upper(p_uf))
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

REVOKE ALL ON FUNCTION api.catalogo() FROM PUBLIC;
REVOKE ALL ON FUNCTION api.nominata(smallint, text, text, integer, text, bigint, integer, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.votacao(smallint, text, text, integer, boolean, smallint, text, bigint, integer, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.comparecimento(smallint, text, text, integer, boolean, smallint) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.eleitorado(smallint, text, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.coligacao(smallint, text, text, integer, text, bigint, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION api.vagas(smallint, text, text, integer, integer) FROM PUBLIC;
