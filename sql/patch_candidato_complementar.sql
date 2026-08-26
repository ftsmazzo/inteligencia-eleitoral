-- Complemento de candidatura (TSE): redes sociais e bens

CREATE TABLE IF NOT EXISTS eleicao.rede_social (
  ano               smallint NOT NULL,
  sq_candidato      bigint NOT NULL,
  nr_ordem          integer NOT NULL DEFAULT 1,
  ds_url            text NOT NULL,
  sg_uf             char(2),
  PRIMARY KEY (ano, sq_candidato, nr_ordem, ds_url)
);

CREATE INDEX IF NOT EXISTS idx_rede_sq ON eleicao.rede_social (ano, sq_candidato);
CREATE INDEX IF NOT EXISTS idx_rede_url ON eleicao.rede_social USING gin (ds_url gin_trgm_ops);

CREATE TABLE IF NOT EXISTS eleicao.bem (
  ano               smallint NOT NULL,
  sq_candidato      bigint NOT NULL,
  nr_ordem          integer NOT NULL,
  cd_tipo_bem       smallint,
  ds_tipo_bem       text,
  ds_bem            text,
  vr_bem            numeric(18, 2),
  PRIMARY KEY (ano, sq_candidato, nr_ordem)
);

CREATE INDEX IF NOT EXISTS idx_bem_sq ON eleicao.bem (ano, sq_candidato);

COMMENT ON TABLE eleicao.rede_social IS
  'URLs/handles oficiais do TSE (rede_social_candidato). Sem scrap.';
COMMENT ON TABLE eleicao.bem IS
  'Bens declarados (bem_candidato). API não deve expor placa/endereço em ds_bem.';
