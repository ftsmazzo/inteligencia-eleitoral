-- CadÚnico e Bolsa Família municipal (contexto social MDS; não urna).

CREATE SCHEMA IF NOT EXISTS contexto;

CREATE TABLE IF NOT EXISTS contexto.cadunico_mun (
  anomes                      integer NOT NULL,
  cod_ibge                    integer NOT NULL REFERENCES ref.municipio (cod_ibge),
  qt_familias                 integer,
  qt_familias_ate_meio_sm     integer,
  qt_familias_acima_meio_sm   integer,
  qt_familias_pobreza_pbf     integer,
  qt_familias_baixa_renda     integer,
  qt_familias_extrema_pobreza integer,
  qt_pessoas_ate_meio_sm      integer,
  qt_pessoas_acima_meio_sm    integer,
  taxa_atualizacao_ate_meio_sm numeric(8, 2),
  PRIMARY KEY (anomes, cod_ibge)
);

CREATE INDEX IF NOT EXISTS idx_cadunico_anomes ON contexto.cadunico_mun (anomes);

CREATE TABLE IF NOT EXISTS contexto.bolsa_familia_mun (
  anomes                   integer NOT NULL,
  cod_ibge                 integer NOT NULL REFERENCES ref.municipio (cod_ibge),
  qt_familias              integer,
  qt_pessoas               integer,
  vr_repassado             numeric(18, 2),
  vr_medio_beneficio       numeric(18, 2),
  pct_familias_rf_mulher   numeric(8, 2),
  PRIMARY KEY (anomes, cod_ibge)
);

CREATE INDEX IF NOT EXISTS idx_bolsa_anomes ON contexto.bolsa_familia_mun (anomes);

COMMENT ON TABLE contexto.cadunico_mun IS
  'Cadastro Único municipal (MDS/CECAD). Competência anomes YYYYMM; um snapshot por carga.';
COMMENT ON TABLE contexto.bolsa_familia_mun IS
  'Bolsa Família municipal (repasse). Competência anomes YYYYMM; um snapshot por carga.';
