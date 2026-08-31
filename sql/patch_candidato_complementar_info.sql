-- Informações complementares TSE (consulta_cand_complementar)

CREATE TABLE IF NOT EXISTS eleicao.candidato_complementar (
  ano                         smallint NOT NULL,
  sq_candidato                bigint NOT NULL,
  sg_uf                       char(2),
  ds_nacionalidade            text,
  nr_idade_data_posse         smallint,
  st_quilombola               text,
  ds_etnia_indigena           text,
  vr_despesa_max_campanha     numeric(18, 2),
  st_reeleicao                text,
  st_declarar_bens            text,
  ds_detalhe_situacao_cand    text,
  ds_situacao_candidato_pleito text,
  ds_situacao_candidato_urna  text,
  st_candidato_inserido_urna  text,
  st_prest_contas             text,
  st_substituido              text,
  ds_situacao_julgamento      text,
  ds_situacao_cassacao        text,
  ds_situacao_diploma         text,
  ds_genero_fefc              text,
  ds_cor_raca_fefc            text,
  PRIMARY KEY (ano, sq_candidato)
);

CREATE INDEX IF NOT EXISTS idx_cand_comp_uf
  ON eleicao.candidato_complementar (ano, sg_uf);

COMMENT ON TABLE eleicao.candidato_complementar IS
  'Campos extras TSE (consulta_cand_complementar). Sem CPF.';
