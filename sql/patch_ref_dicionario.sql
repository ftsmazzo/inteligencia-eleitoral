-- Dicionário de indicadores (FONTES-NUCLEO §0). Evita confundir métricas.

CREATE TABLE IF NOT EXISTS ref.dicionario_indicador (
  id_indicador        text PRIMARY KEY,
  nome_exato          text NOT NULL,
  unidade             text NOT NULL,
  schema_tabela       text,
  nao_confundir_com   text,
  ds_fonte            text
);

TRUNCATE ref.dicionario_indicador;

INSERT INTO ref.dicionario_indicador (id_indicador, nome_exato, unidade, schema_tabela, nao_confundir_com, ds_fonte) VALUES
  ('qt_votos', 'Votos nominais na urna', 'votos', 'eleicao.votacao', 'qt_eleitores; qt_aptos; pct de pesquisa', 'TSE resultado'),
  ('pct_validos', 'Percentual sobre votos válidos', 'percentual', 'api.votacao', 'pct sobre aptos ou soma_dois — usar base_pct', 'derivado api'),
  ('qt_eleitores', 'Eleitores no perfil TSE', 'pessoas', 'eleicao.eleitorado', 'comparecimento; aptos no dia', 'TSE eleitorado'),
  ('qt_aptos', 'Eleitores aptos (detalhe urna)', 'pessoas', 'eleicao.detalhe_munzona', 'qt_eleitores cadastro', 'TSE detalhe'),
  ('qt_comparecimento', 'Comparecimento', 'pessoas', 'eleicao.detalhe_munzona', 'qt_eleitores perfil', 'TSE detalhe'),
  ('qt_populacao', 'População residente', 'pessoas', 'contexto.populacao_mun', 'eleitores; famílias CadÚnico', 'IBGE censo/6579'),
  ('qt_familias_cadunico', 'Famílias CadÚnico', 'famílias', 'contexto.cadunico_mun', 'beneficiários Bolsa; eleitores', 'MDS CECAD snapshot'),
  ('qt_familias_bolsa', 'Famílias beneficiárias Bolsa Família', 'famílias', 'contexto.bolsa_familia_mun', 'famílias CadÚnico', 'MDS snapshot'),
  ('vr_repassado_bolsa', 'Valor repassado Bolsa Família', 'BRL', 'contexto.bolsa_familia_mun', 'despesa de campanha', 'MDS snapshot'),
  ('vr_bem_candidato', 'Patrimônio declarado (bens)', 'BRL', 'eleicao.bem', 'receita/despesa de campanha', 'TSE bens'),
  ('coligacao_proporcional', 'Coligação proporcional', 'metadado', 'eleicao.coligacao', 'federação 2018+', 'TSE; quebra 2014≠2018+');

COMMENT ON TABLE ref.dicionario_indicador IS 'Nomes exatos e armadilhas; não substitui cifra.';
