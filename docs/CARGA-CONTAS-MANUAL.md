# Carga manual · prestação de contas (TSE)

O CDN/CKAN do TSE retorna **403** a partir do servidor EasyPanel. Receita/despesa só entra com zip baixado **no navegador** (ou outra rede) e copiado para `data/raw`.

## 1. Baixar (no PC)

Portal Dados Abertos — recurso **“Prestação de contas de candidatos”** (não confundir com órgão partidário):

| Ano | Dataset (portal atual) | Download direto candidatos |
|-----|------------------------|----------------------------|
| 2018 | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2018 | abrir → **Prestação de contas de candidatos** → Baixar |
| 2022 | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022 | https://dadosabertos.tse.jus.br/dataset/dadosabertos-tse-jus-br-dataset-prestacao-de-contas-eleitorais-2022/resource/e45493d5-75df-4ccf-a4b4-7b1f5213577d |

Links curtos `prestacao-de-contas-eleitorais-AAAA` **não funcionam mais** (404). Catálogo: https://dadosabertos.tse.jus.br/dataset/?groups=prestacao-de-contas-eleitorais

URLs CDN de referência: `docs/DOWNLOAD-COMPLEMENTAR.md`.

## 2. Promover para `data/raw`

Copie os `.zip` para `inbox/contas/` (ex.: `contas_2018.zip`, `contas_2022.zip`) e rode:

```bash
python scripts/promover_contas_inbox.py
```

Destino canônico: `data/raw/br_cand_contas/ano=AAAA/origem.zip` + `meta.json` + SHA-256.

## 3. Carregar no Postgres

Com `DATABASE_URL` no `.env` (porta exposta do Postgres ou rede interna):

```bash
python scripts/carregar_contas.py 2014 2016 2018 2020 2022 2024
```

**Atenção:** `carregar_contas.py` faz `TRUNCATE` em `eleicao.receita` e `eleicao.despesa` antes da carga — passe **todos** os anos que devem permanecer.

## Status (2026-08-29)

Carregado no Postgres: **2014, 2016, 2018, 2020, 2022, 2024** (~9,8M receitas · ~20,2M despesas).

## 4. Validar

```bash
curl -s -H "Authorization: Bearer $MCP_TOKEN" -H "Content-Type: application/json" \
  -d '{"ano":2022,"uf":"SP","limite":3}' \
  https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/v1/receita
```

Status `ok` com linhas = carga OK. Status `vazio` = zip ausente ou ano não carregado.

## Alternativa: job EasyPanel (só carga)

1. Zips já em `data/raw` no volume do serviço `ingest-complementos`
2. Variável `INGEST_SKIP_DOWNLOAD=1` ou deploy com comando:
   `python scripts/job_complementos.py --skip-download --anos-contas 2018,2022`
3. Start → logs devem mostrar linhas em receita (não `skip contas`).
