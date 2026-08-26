-- Módulo parlamentar (Câmara/Senado). Fora do schema eleicao.

CREATE SCHEMA IF NOT EXISTS parlamentar;

CREATE TABLE IF NOT EXISTS parlamentar.deputado (
  id_deputado           integer PRIMARY KEY,
  nome                  text,
  nome_civil            text,
  sigla_sexo            char(1),
  uf_nascimento         char(2),
  municipio_nascimento  text,
  data_nascimento       date,
  id_legislatura_ini    smallint,
  id_legislatura_fim    smallint,
  uri                   text
);

CREATE TABLE IF NOT EXISTS parlamentar.senador (
  id_senador            integer PRIMARY KEY,
  nome_parlamentar      text,
  nome_completo         text,
  sg_partido            text,
  sg_uf                 char(2),
  id_legislatura        smallint,
  em_exercicio          boolean,
  uri                   text
);

CREATE TABLE IF NOT EXISTS parlamentar.proposicao (
  id_proposicao         bigint PRIMARY KEY,
  sg_casa               text NOT NULL DEFAULT 'CD',
  sigla_tipo            text,
  numero                integer,
  ano                   smallint,
  ementa                text,
  data_apresentacao     date,
  id_situacao           integer,
  descricao_situacao    text,
  uri                   text
);

CREATE INDEX IF NOT EXISTS idx_prop_ano ON parlamentar.proposicao (ano);
CREATE INDEX IF NOT EXISTS idx_prop_tipo ON parlamentar.proposicao (sigla_tipo, ano);

CREATE TABLE IF NOT EXISTS parlamentar.proposicao_autor (
  id_proposicao         bigint NOT NULL,
  id_deputado           integer NOT NULL DEFAULT 0,
  nome_autor            text NOT NULL DEFAULT '',
  sg_partido            text,
  sg_uf                 char(2),
  proponente            integer,
  PRIMARY KEY (id_proposicao, id_deputado, nome_autor)
);

CREATE TABLE IF NOT EXISTS parlamentar.votacao (
  id_votacao            text PRIMARY KEY,
  sg_casa               text NOT NULL DEFAULT 'CD',
  data_votacao          timestamptz,
  descricao             text,
  aprovacao             integer,
  ano                   smallint
);

CREATE INDEX IF NOT EXISTS idx_votacao_ano ON parlamentar.votacao (ano);

CREATE TABLE IF NOT EXISTS parlamentar.voto (
  id_votacao            text NOT NULL,
  id_deputado           integer NOT NULL,
  voto                  text,
  sg_partido            text,
  sg_uf                 char(2),
  PRIMARY KEY (id_votacao, id_deputado)
);

CREATE INDEX IF NOT EXISTS idx_voto_dep ON parlamentar.voto (id_deputado);

CREATE TABLE IF NOT EXISTS parlamentar.depara_tse (
  casa                  text NOT NULL CHECK (casa IN ('CD', 'SF')),
  id_casa               integer NOT NULL,
  ano_eleicao           smallint NOT NULL,
  sq_candidato          bigint,
  metodo                text NOT NULL,
  confianca             numeric(5, 2),
  PRIMARY KEY (casa, id_casa, ano_eleicao)
);

CREATE TABLE IF NOT EXISTS parlamentar.proposicao_tema (
  id_proposicao         bigint NOT NULL,
  cod_tema              integer NOT NULL,
  tema                  text,
  relevancia            text,
  PRIMARY KEY (id_proposicao, cod_tema)
);

CREATE INDEX IF NOT EXISTS idx_prop_tema_cod ON parlamentar.proposicao_tema (cod_tema);

CREATE TABLE IF NOT EXISTS parlamentar.orientacao (
  id_votacao            text NOT NULL,
  sigla_bancada         text NOT NULL DEFAULT '',
  orientacao            text,
  sigla_orgao           text,
  PRIMARY KEY (id_votacao, sigla_bancada)
);

CREATE INDEX IF NOT EXISTS idx_orient_vot ON parlamentar.orientacao (id_votacao);

COMMENT ON SCHEMA parlamentar IS 'Atuação Câmara/Senado; não misturar com eleicao.*';
COMMENT ON TABLE parlamentar.depara_tse IS 'Vínculo oficial Casa↔TSE; vazio até carga com método explícito.';
