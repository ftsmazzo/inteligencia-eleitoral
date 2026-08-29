# Carga de propostas de governo (TSE) no acervo

Pipeline no padrão do ingest de contas.

## Scripts

```bash
# 1) Baixa ZIP BR (CDN TSE + fallback CKAN)
python scripts/baixar_propostas_governo.py 2018 2022

# 2) Extrai PDF → texto → seed + Postgres
pip install pypdf
python scripts/carregar_propostas_governo.py 2018 2022
```

Raw: `data/raw/acervo_plano_governo/ano=YYYY/origem.zip`  
Seed: `mcp/seed/acervo_planos_YYYY.jsonl` (bootstrap no `mcp-api`)

## Job EasyPanel

`job_complementos.py` já chama os dois passos. Env:

- `INGEST_ANOS_PROPOSTAS=2018,2022` (padrão)
- `INGEST_SKIP_DOWNLOAD=1` — não baixa de novo (ainda tenta propostas se o ZIP faltar)

Dockerfile: `Dockerfile.ingest` (inclui `pypdf`).

## Fonte

`https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/proposta_governo_{ano}_BR.zip`

## Status 2026-08-29

CDN TSE e CKAN retornaram **HTTP 403** a partir do EasyPanel (`ctl.ingest_log`). Contêiner do ingest ficou em `sleep infinity` para não martelar o TSE.

Workaround manual: colocar o ZIP em  
`data/raw/acervo_plano_governo/ano=2018/origem.zip` (e 2022)  
e rodar `python scripts/carregar_propostas_governo.py 2018 2022` com `DATABASE_URL` apontando para o Postgres.
