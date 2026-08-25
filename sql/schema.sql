-- Inteligência Eleitoral Brasil · DDL v0.1
-- PostgreSQL 16+  ·  sem CHECK Nordeste  ·  urna ≠ série de indicador

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS eleicao;
CREATE SCHEMA IF NOT EXISTS ctl;
CREATE SCHEMA IF NOT EXISTS api;

-- ---------------------------------------------------------------------
-- REF
-- ---------------------------------------------------------------------

CREATE TABLE ref.uf (
  sg_uf     char(2) PRIMARY KEY,
  nome      text NOT NULL,
  regiao    text NOT NULL,
  cd_ibge   smallint
);

INSERT INTO ref.uf (sg_uf, nome, regiao, cd_ibge) VALUES
  ('AC','Acre','Norte',12),
  ('AL','Alagoas','Nordeste',27),
  ('AM','Amazonas','Norte',13),
  ('AP','Amapá','Norte',16),
  ('BA','Bahia','Nordeste',29),
  ('CE','Ceará','Nordeste',23),
  ('DF','Distrito Federal','Centro-Oeste',53),
  ('ES','Espírito Santo','Sudeste',32),
  ('GO','Goiás','Centro-Oeste',52),
  ('MA','Maranhão','Nordeste',21),
  ('MG','Minas Gerais','Sudeste',31),
  ('MS','Mato Grosso do Sul','Centro-Oeste',50),
  ('MT','Mato Grosso','Centro-Oeste',51),
  ('PA','Pará','Norte',15),
  ('PB','Paraíba','Nordeste',25),
  ('PE','Pernambuco','Nordeste',26),
  ('PI','Piauí','Nordeste',22),
  ('PR','Paraná','Sul',41),
  ('RJ','Rio de Janeiro','Sudeste',33),
  ('RN','Rio Grande do Norte','Nordeste',24),
  ('RO','Rondônia','Norte',11),
  ('RR','Roraima','Norte',14),
  ('RS','Rio Grande do Sul','Sul',43),
  ('SC','Santa Catarina','Sul',42),
  ('SE','Sergipe','Nordeste',28),
  ('SP','São Paulo','Sudeste',35),
  ('TO','Tocantins','Norte',17)
ON CONFLICT (sg_uf) DO NOTHING;

CREATE TABLE ref.municipio (
  cod_ibge        integer PRIMARY KEY,
  cd_municipio_tse integer UNIQUE,
  nome            text NOT NULL,
  sg_uf           char(2) NOT NULL REFERENCES ref.uf(sg_uf),
  mesorregiao     text,
  microrregiao    text,
  regiao          text NOT NULL
);

CREATE INDEX idx_municipio_uf ON ref.municipio(sg_uf);
CREATE INDEX idx_municipio_nome ON ref.municipio USING gin (nome gin_trgm_ops);

CREATE TABLE ref.cargo (
  cd_cargo    smallint PRIMARY KEY,
  nome        text NOT NULL,
  esfera      text NOT NULL CHECK (esfera IN ('geral','municipal','distrital')),
  no_recorte  boolean NOT NULL DEFAULT true
);

INSERT INTO ref.cargo (cd_cargo, nome, esfera, no_recorte) VALUES
  (1,  'Presidente',           'geral',      true),
  (2,  'Vice-presidente',      'geral',      false),
  (3,  'Governador',           'geral',      true),
  (4,  'Vice-governador',      'geral',      false),
  (5,  'Senador',              'geral',      true),
  (6,  'Deputado federal',     'geral',      true),
  (7,  'Deputado estadual',    'geral',      true),
  (8,  'Deputado distrital',   'distrital',  true),
  (9,  '1º suplente senador',  'geral',      false),
  (10, '2º suplente senador',  'geral',      false),
  (11, 'Prefeito',             'municipal',  true),
  (12, 'Vice-prefeito',        'municipal',  false),
  (13, 'Vereador',             'municipal',  true)
ON CONFLICT (cd_cargo) DO NOTHING;

CREATE TABLE ref.eleicao (
  ano           smallint NOT NULL,
  esfera        text NOT NULL CHECK (esfera IN ('geral','municipal')),
  ds_eleicao    text,
  tem_resultado boolean NOT NULL DEFAULT true,
  PRIMARY KEY (ano, esfera)
);

INSERT INTO ref.eleicao (ano, esfera, ds_eleicao, tem_resultado) VALUES
  (2014, 'geral',      'Eleições Gerais 2014', true),
  (2016, 'municipal',  'Eleições Municipais 2016', true),
  (2018, 'geral',      'Eleições Gerais 2018', true),
  (2020, 'municipal',  'Eleições Municipais 2020', true),
  (2022, 'geral',      'Eleições Gerais 2022', true),
  (2024, 'municipal',  'Eleições Municipais 2024', true),
  (2026, 'geral',      'Eleições Gerais 2026', false)
ON CONFLICT (ano, esfera) DO NOTHING;

-- ---------------------------------------------------------------------
-- ELEIÇÃO (fatos)
-- ---------------------------------------------------------------------

CREATE TABLE eleicao.candidatura (
  ano               smallint NOT NULL,
  cd_cargo          smallint NOT NULL REFERENCES ref.cargo(cd_cargo),
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer,
  sq_candidato      bigint NOT NULL,
  nr_candidato      integer,
  nm_urna           text,
  nm_candidato      text,
  sg_partido        text,
  nm_coligacao      text,
  ds_situacao       text,
  PRIMARY KEY (ano, sq_candidato)
);

CREATE INDEX idx_cand_uf_cargo ON eleicao.candidatura(ano, sg_uf, cd_cargo);
CREATE INDEX idx_cand_tse ON eleicao.candidatura(ano, cd_municipio_tse) WHERE cd_municipio_tse IS NOT NULL;

CREATE TABLE eleicao.votacao (
  ano               smallint NOT NULL,
  nr_turno          smallint NOT NULL,
  cd_cargo          smallint NOT NULL,
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer NOT NULL,
  nr_zona           integer NOT NULL,
  sq_candidato      bigint NOT NULL,
  nr_candidato      integer,
  nm_urna           text,
  sg_partido        text,
  qt_votos          integer,
  ds_sit_tot_turno  text
) PARTITION BY LIST (ano);

CREATE TABLE eleicao.votacao_2014 PARTITION OF eleicao.votacao FOR VALUES IN (2014);
CREATE TABLE eleicao.votacao_2016 PARTITION OF eleicao.votacao FOR VALUES IN (2016);
CREATE TABLE eleicao.votacao_2018 PARTITION OF eleicao.votacao FOR VALUES IN (2018);
CREATE TABLE eleicao.votacao_2020 PARTITION OF eleicao.votacao FOR VALUES IN (2020);
CREATE TABLE eleicao.votacao_2022 PARTITION OF eleicao.votacao FOR VALUES IN (2022);
CREATE TABLE eleicao.votacao_2024 PARTITION OF eleicao.votacao FOR VALUES IN (2024);

CREATE UNIQUE INDEX uq_votacao_2014 ON eleicao.votacao_2014 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);
CREATE UNIQUE INDEX uq_votacao_2016 ON eleicao.votacao_2016 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);
CREATE UNIQUE INDEX uq_votacao_2018 ON eleicao.votacao_2018 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);
CREATE UNIQUE INDEX uq_votacao_2020 ON eleicao.votacao_2020 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);
CREATE UNIQUE INDEX uq_votacao_2022 ON eleicao.votacao_2022 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);
CREATE UNIQUE INDEX uq_votacao_2024 ON eleicao.votacao_2024 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona, sq_candidato);

CREATE INDEX idx_vot_2014_uf ON eleicao.votacao_2014 (sg_uf, cd_cargo);
CREATE INDEX idx_vot_2016_uf ON eleicao.votacao_2016 (sg_uf, cd_cargo);
CREATE INDEX idx_vot_2018_uf ON eleicao.votacao_2018 (sg_uf, cd_cargo);
CREATE INDEX idx_vot_2020_uf ON eleicao.votacao_2020 (sg_uf, cd_cargo);
CREATE INDEX idx_vot_2022_uf ON eleicao.votacao_2022 (sg_uf, cd_cargo);
CREATE INDEX idx_vot_2024_uf ON eleicao.votacao_2024 (sg_uf, cd_cargo);

CREATE INDEX idx_vot_2014_mun ON eleicao.votacao_2014 (cd_municipio_tse, cd_cargo);
CREATE INDEX idx_vot_2016_mun ON eleicao.votacao_2016 (cd_municipio_tse, cd_cargo);
CREATE INDEX idx_vot_2018_mun ON eleicao.votacao_2018 (cd_municipio_tse, cd_cargo);
CREATE INDEX idx_vot_2020_mun ON eleicao.votacao_2020 (cd_municipio_tse, cd_cargo);
CREATE INDEX idx_vot_2022_mun ON eleicao.votacao_2022 (cd_municipio_tse, cd_cargo);
CREATE INDEX idx_vot_2024_mun ON eleicao.votacao_2024 (cd_municipio_tse, cd_cargo);

CREATE TABLE eleicao.detalhe_munzona (
  ano               smallint NOT NULL,
  nr_turno          smallint NOT NULL,
  cd_cargo          smallint NOT NULL,
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer NOT NULL,
  nr_zona           integer NOT NULL,
  qt_aptos          integer,
  qt_comparecimento integer,
  qt_abstencoes     integer,
  qt_votos_brancos  integer,
  qt_votos_nulos    integer,
  qt_votos_nominais integer,
  qt_votos_legenda  integer
) PARTITION BY LIST (ano);

CREATE TABLE eleicao.detalhe_2014 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2014);
CREATE TABLE eleicao.detalhe_2016 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2016);
CREATE TABLE eleicao.detalhe_2018 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2018);
CREATE TABLE eleicao.detalhe_2020 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2020);
CREATE TABLE eleicao.detalhe_2022 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2022);
CREATE TABLE eleicao.detalhe_2024 PARTITION OF eleicao.detalhe_munzona FOR VALUES IN (2024);

CREATE UNIQUE INDEX uq_det_2014 ON eleicao.detalhe_2014 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);
CREATE UNIQUE INDEX uq_det_2016 ON eleicao.detalhe_2016 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);
CREATE UNIQUE INDEX uq_det_2018 ON eleicao.detalhe_2018 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);
CREATE UNIQUE INDEX uq_det_2020 ON eleicao.detalhe_2020 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);
CREATE UNIQUE INDEX uq_det_2022 ON eleicao.detalhe_2022 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);
CREATE UNIQUE INDEX uq_det_2024 ON eleicao.detalhe_2024 (nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona);

CREATE TABLE eleicao.eleitorado (
  ano               smallint NOT NULL,
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer NOT NULL,
  ds_genero         text,
  ds_faixa_etaria   text,
  ds_grau_escolaridade text,
  qt_eleitores      integer NOT NULL,
  PRIMARY KEY (ano, sg_uf, cd_municipio_tse, ds_genero, ds_faixa_etaria, ds_grau_escolaridade)
);

CREATE TABLE eleicao.coligacao (
  ano               smallint NOT NULL,
  cd_cargo          smallint NOT NULL,
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer,
  sq_coligacao      bigint NOT NULL,
  nm_coligacao      text,
  ds_composicao     text,
  sg_partido        text,
  PRIMARY KEY (ano, sq_coligacao, sg_partido)
);

-- ---------------------------------------------------------------------
-- CTL
-- ---------------------------------------------------------------------

CREATE TABLE ctl.carga (
  id            bigserial PRIMARY KEY,
  id_base       text NOT NULL,
  ano           smallint,
  iniciada_em   timestamptz NOT NULL DEFAULT now(),
  concluida_em  timestamptz,
  linhas        bigint,
  status        text NOT NULL DEFAULT 'em_execucao'
                CHECK (status IN ('em_execucao','sucesso','falha')),
  mensagem      text
);

-- ---------------------------------------------------------------------
-- API (recorte travado)
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION api._ano_no_recorte(p_ano smallint, p_esfera text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM ref.eleicao e
    WHERE e.ano = p_ano AND e.esfera = p_esfera
  );
$$;

CREATE OR REPLACE FUNCTION api.catalogo()
RETURNS TABLE (pacote text, anos text, nota text)
LANGUAGE sql STABLE AS $$
  SELECT * FROM (VALUES
    ('votacao', '2014,2016,2018,2020,2022,2024', 'mun/zona; municipal sem DF'),
    ('comparecimento', '2014,2016,2018,2020,2022,2024', 'detalhe da apuração'),
    ('nominata', '2014–2026', '2026 candidatura viva, sem resultado'),
    ('eleitorado', '2014–2026', 'perfil no ano da urna'),
    ('malha', 'IBGE vigente', '5.571 municípios')
  ) AS t(pacote, anos, nota);
$$;

COMMENT ON FUNCTION api.catalogo IS
  'Recorte: Brasil; Pres a Ver; gerais 2014/2018/2022 + 2026 viva; municipais 2016/2020/2024.';
