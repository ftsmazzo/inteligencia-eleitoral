-- Linha partidária: siglas equivalentes no tempo (TSE).
-- Pedido "PL" inclui PR/PSL; "MDB" inclui PMDB; etc.

CREATE TABLE IF NOT EXISTS ref.partido_linha (
  id_linha    text NOT NULL,
  sg_partido  text NOT NULL,
  nota        text NOT NULL DEFAULT '',
  PRIMARY KEY (id_linha, sg_partido)
);

CREATE INDEX IF NOT EXISTS idx_partido_linha_sg ON ref.partido_linha (sg_partido);

TRUNCATE ref.partido_linha;

INSERT INTO ref.partido_linha (id_linha, sg_partido, nota) VALUES
  -- PL (ex-PR) + incorporação do PSL
  ('pl', 'PL', 'Partido Liberal (atual)'),
  ('pl', 'PR', 'Partido da República → PL (2019)'),
  ('pl', 'PSL', 'PSL incorporado ao PL (2022); em 2018 muitos eleitos bolsonaristas estavam no PSL'),
  -- MDB
  ('mdb', 'MDB', 'Movimento Democrático Brasileiro (atual)'),
  ('mdb', 'PMDB', 'PMDB → MDB (2017)'),
  -- UNIÃO Brasil (DEM + parte do PSL; PSL não entra aqui para evitar dupla contagem com PL)
  ('uniao', 'UNIÃO', 'UNIÃO Brasil (atual)'),
  ('uniao', 'UNIAO', 'variante sem acento'),
  ('uniao', 'DEM', 'Democratas → UNIÃO (2021)'),
  ('uniao', 'PFL', 'PFL → DEM (2007)'),
  -- Republicanos
  ('republicanos', 'REPUBLICANOS', 'Republicanos (atual)'),
  ('republicanos', 'PRB', 'PRB → Republicanos (2019)'),
  -- Progressistas
  ('pp', 'PP', 'Progressistas (atual)'),
  ('pp', 'PPB', 'PPB → PP'),
  -- Podemos
  ('podemos', 'PODEMOS', 'Podemos (atual)'),
  ('podemos', 'PODE', 'sigla curta'),
  ('podemos', 'PTN', 'PTN → Podemos'),
  ('podemos', 'PHS', 'PHS incorporado ao Podemos'),
  -- Cidadania
  ('cidadania', 'CIDADANIA', 'Cidadania (atual)'),
  ('cidadania', 'PPS', 'PPS → Cidadania (2019)'),
  -- Avante
  ('avante', 'AVANTE', 'Avante (atual)'),
  ('avante', 'PT do B', 'PTdoB → Avante'),
  ('avante', 'PTDOB', 'variante'),
  -- Solidariedade
  ('solidariedade', 'SOLIDARIEDADE', 'Solidariedade (atual)'),
  ('solidariedade', 'SD', 'sigla curta'),
  -- Patriota / PRD (fusão recente fora do núcleo de urna; mapeia Patriota/PEN)
  ('patriota', 'PATRIOTA', 'Patriota'),
  ('patriota', 'PEN', 'PEN → Patriota'),
  -- Agir
  ('agir', 'AGIR', 'Agir (atual)'),
  ('agir', 'PTC', 'PTC → Agir'),
  -- DC
  ('dc', 'DC', 'Democracia Cristã (atual)'),
  ('dc', 'PSDC', 'PSDC → DC'),
  -- Rede / Novo / estáveis (auto-linha para normalização)
  ('rede', 'REDE', 'Rede Sustentabilidade'),
  ('novo', 'NOVO', 'Partido Novo'),
  ('pt', 'PT', 'Partido dos Trabalhadores'),
  ('psdb', 'PSDB', 'PSDB'),
  ('pdt', 'PDT', 'PDT'),
  ('psb', 'PSB', 'PSB'),
  ('pcdob', 'PCdoB', 'PCdoB'),
  ('pcdob', 'PCDOB', 'variante'),
  ('psol', 'PSOL', 'PSOL'),
  ('pv', 'PV', 'PV'),
  ('pcb', 'PCB', 'PCB'),
  ('pstu', 'PSTU', 'PSTU'),
  ('pco', 'PCO', 'PCO'),
  ('up', 'UP', 'Unidade Popular'),
  ('mbd_livre', 'MOBILIZA', 'Mobiliza'),
  ('mbd_livre', 'PPL', 'PPL (histórico)')
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION api.siglas_equivalentes(p_sg text)
RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = api, ref, pg_temp
AS $$
  WITH pedida AS (
    SELECT upper(btrim(COALESCE(p_sg, ''))) AS sg
  ),
  linha AS (
    SELECT DISTINCT pl.id_linha
    FROM ref.partido_linha pl
    JOIN pedida p ON upper(pl.sg_partido) = p.sg
  )
  SELECT COALESCE(
    (
      SELECT array_agg(DISTINCT upper(pl.sg_partido) ORDER BY upper(pl.sg_partido))
      FROM ref.partido_linha pl
      WHERE pl.id_linha IN (SELECT id_linha FROM linha)
    ),
    CASE WHEN (SELECT sg FROM pedida) = '' THEN NULL
         ELSE ARRAY[(SELECT sg FROM pedida)] END
  );
$$;

CREATE OR REPLACE FUNCTION api.partido_match(p_filtro text, p_valor text)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
  SELECT p_filtro IS NULL
      OR btrim(p_filtro) = ''
      OR upper(btrim(p_valor)) = ANY (api.siglas_equivalentes(p_filtro));
$$;

CREATE OR REPLACE FUNCTION api.ufs_da_regiao(p_regiao text)
RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = api, ref, pg_temp
AS $$
  SELECT COALESCE(array_agg(u.sg_uf ORDER BY u.sg_uf), ARRAY[]::text[])
  FROM ref.uf u
  WHERE upper(u.regiao) = upper(btrim(COALESCE(p_regiao, '')))
     OR (
       upper(btrim(COALESCE(p_regiao, ''))) IN ('NE', 'NORDESTE')
       AND u.regiao = 'Nordeste'
     )
     OR (
       upper(btrim(COALESCE(p_regiao, ''))) IN ('NORTE')
       AND u.regiao = 'Norte'
     )
     OR (
       upper(btrim(COALESCE(p_regiao, ''))) IN ('SUDESTE')
       AND u.regiao = 'Sudeste'
     )
     OR (
       upper(btrim(COALESCE(p_regiao, ''))) IN ('SUL')
       AND u.regiao = 'Sul'
     )
     OR (
       upper(btrim(COALESCE(p_regiao, ''))) IN ('CENTRO-OESTE', 'CENTRO_OESTE', 'CENTROOESTE', 'CO')
       AND u.regiao = 'Centro-Oeste'
     );
$$;

CREATE OR REPLACE FUNCTION api.eh_regiao(p_uf text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT upper(btrim(COALESCE(p_uf, ''))) IN (
    'NORDESTE','NE','NORTE','SUDESTE','SUL',
    'CENTRO-OESTE','CENTRO_OESTE','CENTROOESTE','CO'
  );
$$;

CREATE OR REPLACE FUNCTION api.uf_match(p_filtro text, p_valor text)
RETURNS boolean
LANGUAGE sql STABLE
AS $$
  SELECT p_filtro IS NULL
      OR btrim(p_filtro) = ''
      OR (
        NOT api.eh_regiao(p_filtro)
        AND upper(btrim(p_valor)) = upper(btrim(p_filtro))
      )
      OR (
        api.eh_regiao(p_filtro)
        AND upper(btrim(p_valor)) = ANY (api.ufs_da_regiao(p_filtro))
      );
$$;

COMMENT ON TABLE ref.partido_linha IS 'Famílias de siglas equivalentes no tempo (TSE). Usado por api.siglas_equivalentes.';
COMMENT ON FUNCTION api.siglas_equivalentes(text) IS 'Dada uma sigla pedida, devolve todas as equivalentes na mesma linha partidária.';

GRANT SELECT ON ref.partido_linha TO agente;
GRANT EXECUTE ON FUNCTION api.siglas_equivalentes(text) TO agente;
GRANT EXECUTE ON FUNCTION api.partido_match(text, text) TO agente;
GRANT EXECUTE ON FUNCTION api.ufs_da_regiao(text) TO agente;
GRANT EXECUTE ON FUNCTION api.eh_regiao(text) TO agente;
GRANT EXECUTE ON FUNCTION api.uf_match(text, text) TO agente;
