# Dados · uma árvore só

Espelha a spec: raw imutável → staging Parquet → Postgres.  
Não gravar na raiz. Não copiar a árvore da campanha (`ne9`, SQLite de urna, pastas soltas).

```
data/
  raw/<id_base>/<YYYY-MM-DD>/
    origem.zip          # bytes da fonte, sem editar
    origem.sha256
    meta.json           # url, orgao, recorte, id_execucao
  staging/<id_base>/
    ano=YYYY/*.parquet  # formato longo; NULL ≠ 0
  qa/<id_base>/
    ancora.json         # esperado vs obtido
```

`id_base` usa os ids de `docs/FONTES-NUCLEO.md` (`br_mun_votacao_nominal`, não `ne9_mun_eleitoral_resultados_2002_2022`).

Dump desorganizado da outra aplicação vai para `inbox/`, não para cá. Só depois do checklist (FONTES §8) copia-se o arquivo escolhido para `data/raw/<id_base>/<YYYY-MM-DD>/`.

Regra: segundo download do mesmo URL só ocorre se o SHA-256 for diferente.
