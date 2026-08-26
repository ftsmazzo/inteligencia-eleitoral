-- População municipal IBGE (contexto, não urna).
-- Censo nos anos de recenseamento; estimativa nos demais publicados.

CREATE SCHEMA IF NOT EXISTS contexto;

CREATE TABLE IF NOT EXISTS contexto.populacao_mun (
  ano           smallint NOT NULL,
  cod_ibge      integer NOT NULL REFERENCES ref.municipio (cod_ibge),
  qt_populacao  integer NOT NULL,
  ds_fonte      text NOT NULL CHECK (ds_fonte IN ('censo', 'estimativa')),
  PRIMARY KEY (ano, cod_ibge)
);

CREATE INDEX IF NOT EXISTS idx_pop_ano_uf
  ON contexto.populacao_mun (ano);

COMMENT ON TABLE contexto.populacao_mun IS
  'População municipal IBGE: censo (2010, 2022) e estimativas SIDRA 6579. Sem inventar ano sem publicação.';
