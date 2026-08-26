-- Vagas por cargo × território (TSE consulta_vagas)

CREATE TABLE IF NOT EXISTS eleicao.vagas (
  ano               smallint NOT NULL,
  cd_cargo          smallint NOT NULL,
  sg_uf             char(2) NOT NULL,
  cd_municipio_tse  integer NOT NULL DEFAULT 0,
  qt_vagas          integer NOT NULL,
  PRIMARY KEY (ano, cd_cargo, sg_uf, cd_municipio_tse)
);

CREATE INDEX IF NOT EXISTS idx_vagas_ano_uf_cargo
  ON eleicao.vagas (ano, sg_uf, cd_cargo);

COMMENT ON COLUMN eleicao.vagas.cd_municipio_tse IS
  'Código TSE do município; 0 = escopo UF ou BR (cargos gerais).';
