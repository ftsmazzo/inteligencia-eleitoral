# Fontes oficiais · núcleo eleitoral Brasil

Recorte: federal/estadual 2014–2022 + 2026 viva; municipal 2016–2024.  
Portal TSE: [dadosabertos.tse.jus.br](https://dadosabertos.tse.jus.br/). Repositório legado (pré-2022, ainda útil para achar zip): [hotsite pesquisas eleitorais](https://www.tse.jus.br/hotsites/pesquisas-eleitorais/index.html).

CDN frequente dos zips: `https://cdn.tse.jus.br/estatistica/sead/odsele/`  
(o nome do arquivo muda; o conjunto no portal é a URL estável).

Quando o raw da outra aplicação for despejado em `inbox/`, classificar cada pasta contra esta lista: **reusar** (mesmo órgão, Brasil, anos do recorte) ou **descartar** (NE9 só, ano fora, hash diferente da fonte, duplicata). Não editar o que estiver em `inbox/`.

---

## 0. Referência (bloqueante — primeiro)

| Id | O que é | Fonte | Link |
|---|---|---|---|
| `br_mun_malha_ibge` | Municípios vigentes, 7 dígitos, UF, meso/micro, região | IBGE Localidades | [API Localidades](https://servicodados.ibge.gov.br/api/docs/localidades) · [municípios](https://servicodados.ibge.gov.br/api/v1/localidades/municipios) |
| `br_depara_tse_ibge` | CD município TSE ↔ IBGE 7 dígitos, 100% da malha | TSE + IBGE | [Portal TSE](https://dadosabertos.tse.jus.br/) (código vem nos CSVs de votação; malha IBGE é a canônica) |
| `ref_dicionario_indicadores` | Nome exato, unidade, `nao_confundir_com` | Próprio | interno |
| `ref_eleicao` | Ano, esfera (geral/municipal), cargos, turnos, quebra metodológica | TSE | derivados dos conjuntos abaixo |

Âncora de malha: conferir contagem IBGE vigente (~5.570 municípios + DF como UF sem municípios “de estado” no mesmo sentido; municípios são os 5.570 da malha). A campanha fechou **1.794** só no NE9 — não reusar esse CSV como Brasil.

---

## 1. Resultado de urna (votação)

Arquivo-chave: **votação nominal por município e zona** + **detalhe da apuração** (aptos, comparecimento, brancos, nulos, válidos).

| Urna | Conjunto no portal | Notas |
|---|---|---|
| 2014 geral | [Resultados 2014](https://dadosabertos.tse.jus.br/dataset/resultados-2014) | Pres, gov, sen, dep fed/est. Coligação proporcional ainda existe. |
| 2016 municipal | [Resultados 2016](https://dadosabertos.tse.jus.br/dataset/resultados-2016) | Pref + ver |
| 2018 geral | [Resultados 2018](https://dadosabertos.tse.jus.br/dataset/resultados-2018) | Sem coligação proporcional (reforma 2017) |
| 2020 municipal | [Resultados 2020](https://dadosabertos.tse.jus.br/dataset/resultados-2020) | Pref + ver |
| 2022 geral | [Resultados 2022](https://dadosabertos.tse.jus.br/dataset/resultados-2022) | Inclui [votação mun/zona](https://dadosabertos.tse.jus.br/dataset/resultados-2022/resource/40fdcf49-256a-4c81-87cf-711545bd1528) |
| 2024 municipal | [Resultados 2024](https://dadosabertos.tse.jus.br/dataset/resultados-2024) | Pref + ver (última urna municipal do recorte) |
| 2026 geral | resultado **ainda não** | Só candidatura até a apuração oficial |

Ids de produto (partição por `ano` + `cargo`, não uma tabela `ne9_*` por cargo):

- `br_mun_votacao_nominal` — votos do candidato na urna, mun/zona  
- `br_mun_detalhe_apuracao` — comparecimento / brancos / nulos / válidos  
- `br_uf_votacao` — agregado UF (calculado da municipal; nunca o inverso)

---

## 2. Candidaturas (nominata)

| Urna | Conjunto | Link |
|---|---|---|
| 2014 | Candidatos 2014 | [candidatos-2014](https://dadosabertos.tse.jus.br/dataset/candidatos-2014) |
| 2016 | Candidatos 2016 | [candidatos-2016](https://dadosabertos.tse.jus.br/dataset/candidatos-2016) |
| 2018 | Candidatos 2018 | [candidatos-2018](https://dadosabertos.tse.jus.br/dataset/candidatos-2018) |
| 2020 | Candidatos 2020 | [candidatos-2020](https://dadosabertos.tse.jus.br/dataset/candidatos-2020) |
| 2022 | Candidatos 2022 | [candidatos-2022](https://dadosabertos.tse.jus.br/dataset/candidatos-2022) |
| 2024 | Candidatos 2024 | [candidatos-2024](https://dadosabertos.tse.jus.br/dataset/candidatos-2024) |
| 2026 | Candidatos 2026 (camada viva) | [candidatos-2026](https://dadosabertos.tse.jus.br/dataset/candidatos-2026) |

Id: `br_cand_nominata` — situação, partido, cargo (sem CPF completo na API).

No mesmo conjunto **Candidatos – AAAA** o TSE publica pacotes irmãos (entrar no próximo bloco após a urna):

| Id | Recurso no portal | Uso |
|---|---|---|
| `br_cand_bens` | Bens de candidatos | Patrimônio declarado; entra com prestação de contas |
| `br_cand_contas` | Prestação de contas (candidatos) | Receitas/despesas oficiais |
| `br_cand_rede_social` | Redes sociais | **Opcional / depois** — anos faltantes quebram o fluxo |
| `br_cand_complementar` | Informações complementares | **Opcional / depois** |
| `br_cand_vagas` | Vagas | Já no núcleo de urna |
| `br_cand_coligacao` | Coligações | Já no núcleo de urna |

Fotos, certidões e notas fiscais: só se houver demanda explícita (peso/PII). Motivo de cassação: útil como metadado de situação, não como cifra de urna.

DivulgaCand (consulta pontual, não substitui o zip): [divulgacandcontas.tse.jus.br](https://divulgacandcontas.tse.jus.br/)

---

## 3. Perfil do eleitorado

Conjuntos “eleitorado” / perfil por município (sexo, faixa, escolaridade). Portal: buscar `eleitorado` + ano em [dataset](https://dadosabertos.tse.jus.br/dataset/).

Exemplos estáveis por ano (conferir o slug no portal se o TSE renomear):

- [Eleitorado 2014](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2014)  
- [Eleitorado 2016](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2016)  
- [Eleitorado 2018](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2018)  
- [Eleitorado 2020](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2020)  
- [Eleitorado 2022](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2022)  
- [Eleitorado 2024](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2024)  
- [Eleitorado 2026](https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2026) (cadastro ≠ apto do dia da urna)

Id: `br_mun_eleitorado_perfil` — só anos de urna do recorte. Cadastro 2026 não é resultado 2026.

---

## 4. Prestação de contas de campanha

Portal + DivulgaCand:

- Busca: [prestação / contas no Dados Abertos](https://dadosabertos.tse.jus.br/dataset/?q=prestacao+contas)  
- Interface: [DivulgaCandContas](https://divulgacandcontas.tse.jus.br/)

Id: `br_cand_contas` — receitas/despesas do candidato; doador identificado só se a publicação oficial exigir e sem PII extra. Órgão partidário é tabela irmã, não misturar com candidato.

---

## 5. Mapa político (eleitos) — **não é download novo**

Governador, prefeito, vereador, deputados, senadores **eleitos** saem da votação + situação de candidatura dos conjuntos das seções 1 e 2. Não há fonte oficial separada “lista de vereadores” além do TSE.

Atuação parlamentar (proposições, votos) é **módulo posterior**, Câmara/Senado, fora do núcleo de urna:

- [Dados Abertos Câmara](https://dadosabertos.camara.leg.br/)  
- [Dados Abertos Senado](https://www12.senado.leg.br/dados-abertos)

---

## 6. Demografia (contexto, não urna)

Só se o MVP incluir cruzamento eleitorado × população. Janela da fonte, não 2014–2026 forçado.

| Id | Fonte | Link |
|---|---|---|
| `br_mun_censo` | IBGE Censo 2010 e 2022 | [SIDRA](https://sidra.ibge.gov.br/) tabelas 1378 (2010) e 4709 (2022) |
| `br_mun_estimativas` | Estimativas populacionais | [SIDRA 6579](https://sidra.ibge.gov.br/tabela/6579) · anos sem censo (ex.: 2014–2021, 2024–2025). **Sem inventar 2023/2026.** |

Tabela canônica: `contexto.populacao_mun` (`ds_fonte` = `censo` \| `estimativa`). API: `api.populacao`.

---

## 6b. Social municipal (MDS) — contexto, não urna

Reuso do `inbox/` (Brasil municipal, um mês). Não misturar com votação.

| Id | Fonte | Competência nesta carga |
|---|---|---|
| `br_mun_cadunico` | Cadastro Único (CECAD/MDS) | `anomes=202607` |
| `br_mun_bolsa_familia` | Bolsa Família municipal | `anomes=202608` |

Tabelas: `contexto.cadunico_mun`, `contexto.bolsa_familia_mun`. APIs: `api.cadunico`, `api.bolsa_familia`. CSV usa IBGE 6 dígitos → malha 7. `inbox/bolsa/` (HTML/scrap) **não** entra.

## 7. Fora do núcleo (não baixar “para completar”)

| Tema | Motivo | Link só para registrar a lacuna |
|---|---|---|
| Portos ANTAQ | Painel/SDP em manutenção | [ANTAQ dados](https://www.gov.br/antaq/pt-br) |
| MVI municipal | FBSP publica UF | [Fórum Brasileiro de Segurança Pública](https://forumseguranca.org.br/) |
| Influenciadores | Sem fonte oficial | — |
| Pós-colheita | Sem cadastro nacional | — |
| Pesquisas de intenção | Não é urna; se entrar um dia, registro TSE ≠ % de instituto | [Registro de pesquisas TSE](https://divulgacandcontas.tse.jus.br/) |

---

## 8. Reuso vs download (quando o raw da outra aplicação chegar)

**Candidato a reuso:** zip TSE Brasil dos anos 2014, 2016, 2018, 2020, 2022, 2024; `consulta_cand` 2026 Brasil; malha IBGE nacional; de-para com 27 UF; Parquet já no formato longo com `cod_ibge` 7 dígitos.

**Descartar como canônico:** CSV só NE9; SQLite de urna com grafia duplicada (Quijingue/Ereré/Arez); qualquer `ne9_*` como nome de fato Brasil; clipping vazio; dossiê de personagem da chapa; ICE/Quadro Geral; hash que não bate com o zip atual do portal.

**Não misturar:** Base dos Dados como atalho de extração é opcional ([br-tse-eleicoes](https://basedosdados.org/dataset/br-tse-eleicoes)), mas a âncora e a citação são sempre TSE/IBGE.
