-- Prestação de contas de candidatos (TSE). CPF não entra na API.

CREATE TABLE IF NOT EXISTS eleicao.receita (
  id                bigserial PRIMARY KEY,
  ano               smallint NOT NULL,
  sq_candidato      bigint,
  sg_uf             char(2),
  sg_partido        text,
  nr_candidato      integer,
  ds_cargo          text,
  nm_candidato      text,
  sq_receita        bigint,
  dt_receita        date,
  vr_receita        numeric(18, 2) NOT NULL,
  ds_fonte          text,
  ds_origem         text,
  ds_especie        text,
  ds_receita        text,
  nm_doador         text,
  sg_partido_doador text
);

CREATE INDEX IF NOT EXISTS idx_receita_ano_cand ON eleicao.receita (ano, sq_candidato);
CREATE INDEX IF NOT EXISTS idx_receita_ano_uf ON eleicao.receita (ano, sg_uf);
CREATE INDEX IF NOT EXISTS idx_receita_sq ON eleicao.receita (ano, sq_receita) WHERE sq_receita IS NOT NULL;

CREATE TABLE IF NOT EXISTS eleicao.despesa (
  id                bigserial PRIMARY KEY,
  ano               smallint NOT NULL,
  sq_candidato      bigint,
  sg_uf             char(2),
  sg_partido        text,
  nr_candidato      integer,
  ds_cargo          text,
  nm_candidato      text,
  sq_despesa        bigint,
  dt_despesa        date,
  vr_despesa        numeric(18, 2) NOT NULL,
  ds_origem         text,
  ds_despesa        text,
  nm_fornecedor     text
);

CREATE INDEX IF NOT EXISTS idx_despesa_ano_cand ON eleicao.despesa (ano, sq_candidato);
CREATE INDEX IF NOT EXISTS idx_despesa_ano_uf ON eleicao.despesa (ano, sg_uf);
CREATE INDEX IF NOT EXISTS idx_despesa_sq ON eleicao.despesa (ano, sq_despesa) WHERE sq_despesa IS NOT NULL;

COMMENT ON TABLE eleicao.receita IS 'Receitas de campanha do candidato (prestação TSE).';
COMMENT ON TABLE eleicao.despesa IS 'Despesas contratadas/declaradas do candidato (prestação TSE).';
