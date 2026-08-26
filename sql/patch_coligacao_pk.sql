-- Grão correto: eleição × cargo × UF × município (0 = escopo UF/BR) × coligação × partido

ALTER TABLE eleicao.coligacao DROP CONSTRAINT IF EXISTS coligacao_pkey;

ALTER TABLE eleicao.coligacao
  ALTER COLUMN cd_municipio_tse SET NOT NULL,
  ALTER COLUMN cd_municipio_tse SET DEFAULT 0;

UPDATE eleicao.coligacao SET cd_municipio_tse = 0 WHERE cd_municipio_tse IS NULL;

ALTER TABLE eleicao.coligacao
  ADD PRIMARY KEY (ano, cd_cargo, sg_uf, cd_municipio_tse, sq_coligacao, sg_partido);

CREATE INDEX IF NOT EXISTS idx_colig_ano_cargo_uf
  ON eleicao.coligacao (ano, sg_uf, cd_cargo);

CREATE INDEX IF NOT EXISTS idx_colig_partido
  ON eleicao.coligacao (ano, sg_partido, cd_cargo);

COMMENT ON COLUMN eleicao.coligacao.cd_municipio_tse IS
  'Código TSE do município; 0 = escopo UF ou BR (cargos gerais).';
