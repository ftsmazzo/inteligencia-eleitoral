# Downloads · bens + prestação de contas

Redes sociais e informações complementares **ficam de fora deste fluxo** (lacuna por ano; não bloqueiam).

## 1. Bens (`br_cand_bens`)

Pasta: `data/raw/br_cand_bens/ano=AAAA/origem.zip`

| Ano | CDN | Portal |
|---|---|---|
| 2014 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2014.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2014 |
| 2016 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2016.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2016 |
| 2018 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2018.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2018 |
| 2020 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2020.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2020 |
| 2022 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2022.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2022 |
| 2024 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2024.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2024 |
| 2026 | https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2026.zip | https://dadosabertos.tse.jus.br/dataset/candidatos-2026 |

## 2. Prestação de contas — candidatos (`br_cand_contas`)

Conjunto separado no portal (não é o zip de “Candidatos”).  
Pasta: `data/raw/br_cand_contas/ano=AAAA/origem.zip`

Baixe o recurso **“Prestação de contas de candidatos”** (receitas/despesas). **Não** misturar órgão partidário no mesmo id.

| Ano | CDN (candidatos) | Portal (dataset) | Recurso candidatos |
|---|---|---|---|
| 2014 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2014.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2014 | abrir dataset → **Prestação de contas de candidatos** |
| 2016 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2016.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2016 | idem |
| 2018 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2018.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2018 | idem |
| 2020 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2020.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2020 | idem |
| 2022 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2022.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022 | [recurso candidatos 2022](https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022/resource/e45493d5-75df-4ccf-a4b4-7b1f5213577d) |
| 2024 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2024.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2024 | idem |
| 2026 | https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2026 | idem |

**Nota:** URLs curtas `prestacao-de-contas-eleitorais-AAAA` **retornam 404** no portal atual. Use o slug `dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-AAAA` ou a [busca por grupo](https://dadosabertos.tse.jus.br/dataset/?groups=prestacao-de-contas-eleitorais).

Se o nome no CDN mudar, use o botão do portal. Zips grandes (GB) são normais.

## Fora deste fluxo

- Extratos bancários / órgão partidário — irmãos, não misturar com `br_cand_contas`

## Redes e complementar (carga manual)

Dados em `inbox/dados-manuais` → `data/raw/br_cand_rede_social` e `br_cand_complementar` → Postgres.

```bash
python scripts/promover_dados_manuais.py
python scripts/carregar_rede_social.py 2020 2022 2024 2026
python scripts/carregar_candidato_complementar.py 2018 2020 2022 2024 2026
```

API/MCP: `rede_social`, `complementar` (exige `ano` + `sq_candidato`).
