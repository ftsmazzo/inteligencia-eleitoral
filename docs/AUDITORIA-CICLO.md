# Auditoria do ciclo eleitoral · 25/08/2026

Nada foi carregado no banco. CDN TSE respondeu **403** desta máquina (mesmo bloqueio da campanha). Os 13 pacotes faltantes vão por download no navegador.

## O que já está em `data/raw` (Brasil completo, zip)

| Pacote | Anos no disco |
|---|---|
| `br_mun_malha_ibge` | 5.571 municípios (`municipios.json`) |
| `br_mun_votacao_nominal` | 2014, 2018, 2022, 2024 |
| `br_mun_detalhe_apuracao` | 2018, 2022 |
| `br_cand_nominata` | 2018, 2020, 2022, 2024, 2026 |
| `br_cand_coligacao` | 2018, 2020, 2022, 2024, 2026 |
| `br_cand_vagas` | 2026 |
| `br_mun_eleitorado_perfil` | 2014, 2018, 2022, 2026 |

Inbox: saíram urna 1998–2010, CSV só NE, duplicatas e os zips já copiados. Restou o que **não** é este ciclo (saúde, CAGED, Câmara, processos, ANTAQ, etc.). Emendas que estavam dentro de `resultados/` foram para `inbox/emendas/`.

## Ciclo que precisa fechar antes de qualquer carga

Sem estes anos o recorte 2014–2026 / municipal 2016–2024 fica picado — o erro da primeira base.

| | 2014 | 2016 | 2018 | 2020 | 2022 | 2024 | 2026 |
|---|---|---|---|---|---|---|---|
| Votação mun/zona | no raw | **baixar** | no raw | **baixar** | no raw | no raw | — (depois da urna) |
| Detalhe apuração | **baixar** | **baixar** | no raw | **baixar** | no raw | **baixar** | — |
| Nominata | **baixar** | **baixar** | no raw | no raw | no raw | no raw | no raw |
| Eleitorado | no raw | **baixar** | no raw | **baixar** | no raw | **baixar** | no raw (cadastro) |
| Coligação | **baixar** | **baixar** | no raw | no raw | no raw | no raw | no raw |

2026 resultado **não** se baixa agora.

---

## Você baixa: URL final → pasta

Salve o arquivo exatamente como `origem.zip` (não deixe o nome original do TSE).

No portal, o botão costuma ser **“Votação nominal por município e zona”**, **“Detalhe da apuração por município e zona”**, **“Candidatos”** / consulta_cand, **“Perfil eleitorado”**, **“Coligações”**.

### 1. Votação 2016 (prefeito/vereador)

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2016  
- CDN (abrir no Chrome): https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2016.zip  
- Pasta: `data/raw/br_mun_votacao_nominal/ano=2016/origem.zip`

### 2. Votação 2020 (prefeito/vereador)

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2020  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2020.zip  
- Pasta: `data/raw/br_mun_votacao_nominal/ano=2020/origem.zip`

### 3. Detalhe da apuração 2014

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2014  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2014.zip  
- Pasta: `data/raw/br_mun_detalhe_apuracao/ano=2014/origem.zip`

### 4. Detalhe 2016

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2016  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2016.zip  
- Pasta: `data/raw/br_mun_detalhe_apuracao/ano=2016/origem.zip`

### 5. Detalhe 2020

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2020  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2020.zip  
- Pasta: `data/raw/br_mun_detalhe_apuracao/ano=2020/origem.zip`

### 6. Detalhe 2024

- Portal: https://dadosabertos.tse.jus.br/dataset/resultados-2024  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip  
- Pasta: `data/raw/br_mun_detalhe_apuracao/ano=2024/origem.zip`

### 7. Nominata 2014

- Portal: https://dadosabertos.tse.jus.br/dataset/candidatos-2014  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2014.zip  
- Pasta: `data/raw/br_cand_nominata/ano=2014/origem.zip`

### 8. Nominata 2016

- Portal: https://dadosabertos.tse.jus.br/dataset/candidatos-2016  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2016.zip  
- Pasta: `data/raw/br_cand_nominata/ano=2016/origem.zip`

### 9. Eleitorado 2016

- Portal: https://dadosabertos.tse.jus.br/dataset/?q=eleitorado+2016  
- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_2016.zip  
- Pasta: `data/raw/br_mun_eleitorado_perfil/ano=2016/origem.zip`

### 10. Eleitorado 2020

- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_2020.zip  
- Pasta: `data/raw/br_mun_eleitorado_perfil/ano=2020/origem.zip`

### 11. Eleitorado 2024

- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_2024.zip  
- Pasta: `data/raw/br_mun_eleitorado_perfil/ano=2024/origem.zip`

### 12. Coligação 2014 (proporcional ainda existia)

- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_coligacao/consulta_coligacao_2014.zip  
- Pasta: `data/raw/br_cand_coligacao/ano=2014/origem.zip`

### 13. Coligação 2016

- CDN: https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_coligacao/consulta_coligacao_2016.zip  
- Pasta: `data/raw/br_cand_coligacao/ano=2016/origem.zip`

Crie a pasta do ano se não existir. Quando os 13 estiverem no lugar, avise: eu confiro tamanho/zip (27 UF) e só então fechamos o ciclo para tratamento — ainda sem Postgres.
