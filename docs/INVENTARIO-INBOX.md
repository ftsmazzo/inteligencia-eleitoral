# Inventário do inbox (despejo intacto)

O `inbox/` **não foi movido nem limpo** — 965 arquivos, ~50 GB. Esta página é o índice do **despejo**: o que entra no núcleo Brasil, o que fica de fora.

**Status de carga (raw + Postgres):** `docs/AUDITORIA-RECORTE.md` e `python scripts/auditar_recorte.py`. Não usar esta página para saber se o banco está completo — ela envelhece rápido.

CSV misturado com PDF é o padrão da campanha: número, acervo e relatório na mesma árvore. Aqui separamos por **uso**, não por extensão.

---

## Núcleo eleitoral (reusar — não baixar de novo, se o zip for Brasil)

### Resultado de urna — `inbox/resultados/`

| Urna | Zip | CSV solto | Decisão |
|---|---|---|---|
| 2014 | `votacao_candidato_munzona_2014.zip` (494 MB) | só NE9 + BR/BRASIL | **Usar o zip**, não a pasta descompactada |
| 2016 municipal | — | — | **Falta.** Download em [Resultados 2016](https://dadosabertos.tse.jus.br/dataset/resultados-2016) |
| 2018 | zip + 30 CSVs (detalhe e votação) | parece malha completa | Reusar zip + detalhe 2018 |
| 2020 municipal | — | — | **Falta.** [Resultados 2020](https://dadosabertos.tse.jus.br/dataset/resultados-2020) |
| 2022 | zip + 30 CSVs | parece malha completa | Reusar |
| 2024 municipal | zip 48 MB + CSV só NE9 | pasta descompactada é Nordeste | Abrir o zip e conferir se tem 27 UF; se for só NE, **baixar de novo o conjunto Brasil** |
| 1998, 2002, 2006, 2010 | zips + CSV | fora do recorte | **Não promover.** Não apagar no inbox |
| `202012_Despesas.zip`, `EmendasParlamentares.zip` | no meio de resultados | fiscal/emenda, não urna | Tratar depois; não misturar com votação |

Comparecimento: só `detalhe_votacao_munzona_2018` e `_2022`. **Faltam detalhe 2014, 2016, 2020, 2024.**

### Nominata e contas — `inbox/persona/` + `inbox/tse/`

Há `consulta_cand` **2018, 2020, 2022, 2024, 2026** (e complementar). **Faltam 2014 e 2016.**

Duplicata: `consulta_cand_2018/2022` também em `tse/`. Contas 2022 estão em `tse/contas/2022/`, não em persona.

Bens: 2018–2026 (sem 2022 CNPJ campanha; sem bens 2014/2016). Extrato bancário e CNPJ de campanha: não são núcleo de urna; PII — não promover sem regra.

`consulta_vagas_2026`, coligações 2018–2026: úteis no recorte; coligação 2014 (quando existia proporcional) **falta**.

### Eleitorado — `inbox/eleitorado/`

Zips: 2002, 2006, 2010 (**fora**), **2014**, 2018, 2022, **2026**. Pastas descompactadas 2018 e 2022.

**Faltam perfil 2016, 2020, 2024.** 2026 é cadastro, não urna.

### Malha — `inbox/ibge/municipios.json`

Candidato a `br_mun_malha_ibge`. Conferir se são ~5.570 (Brasil) e não 1.794 (NE9). `pib_municipio.csv.gz` e PIA/CEMPRE são contexto econômico, não urna.

`inbox/bd/` (Base dos Dados, `.gz`) e `bd_detalhes_votacao_municipio.csv.gz` na raiz: atalho possível; âncora continua TSE.

---

## Fora do núcleo (não organizar para o MVP)

Pastas temáticas da campanha (~metade do volume): ANP, ANEEL, ANM, ANAC, ANA, ANTAQ (PDF — lacuna já declarada), ONS, EPE, CAGED, RAIS, INEP, CNES/SIA/SIH/SIM/SINASC, CadÚnico, Bolsa (UF e `bolsa_mun` 27 UF), SICONFI, transferências, execução federal, emendas, FBSP, SINESP, SISDEPEN, turismo, fertilizantes, USGS, BCB, e-Gestor AB, previdência.

Úteis **depois**, se o produto ganhar bloco social/fiscal. `bolsa_mun` e `cadunico` já vieram **Brasil municipal** (um mês) — não jogar fora; só não misturar com urna.

### PDF / HTML / acervo (trilha B ou recusar)

| Onde | O que é |
|---|---|
| `mapa_orcrim_2024.pdf` (raiz) | Mapa de facção — não é taxa municipal |
| `legislacao_tse/` | PDF + `.bin` + txt |
| `cpmi_inss/` | HTML, PDF, bin — dossiê da chapa |
| `relatorios_tecnicos/` | PDF |
| `antaq/` | PDF (fonte em manutenção) |
| `fbsp/` | xlsx + PDF anuário |
| `sisdepen_bases.html` (raiz) | página, não microdado |

Não copiar PDF para `data/raw` de votação.

### Câmara — `inbox/camara/`

Proposições e votos 2023–2025 + `deputados_ne57.json` (**NE**). Módulo parlamentar posterior, não núcleo de urna.

### Persona processual TSE

Zips `processo_eleitoral_*` em `tse/`: passivo eleitoral; fora do MVP de urna.

### Pesquisas — `pesquisas/`, `tse_pesquisas/`

Não é resultado de urna. Fora do recorte da ferramenta até existir módulo próprio.

---

## Buracos do recorte (baixar de verdade)

1. Resultados **2016** e **2020** (prefeito/vereador).  
2. Detalhe da apuração **2014, 2016, 2020, 2024**.  
3. `consulta_cand` **2014** e **2016**.  
4. Eleitorado **2016, 2020, 2024**.  
5. Confirmar se o zip **2024** é Brasil ou só NE.  
6. Malha IBGE: validar contagem em `municipios.json`.  
7. De-para TSE–IBGE: não há pasta dedicada; extrair dos CSVs de votação + malha.

---

## Como “organizar” sem bagunçar o despejo

1. `inbox/` permanece como está.  
2. Promoção futura: **somente zips** listados como reuso → `data/raw/<id_base>/2026-08-25/` com `meta.json` apontando o caminho original no inbox (cópia, não corte).  
3. CSV descompactado NE9 (2014 e 2024 pastas) **não** sobe para `data/raw`.  
4. PDF não entra na trilha A.

Próximo passo operacional, quando você autorizar: promover os zips 2018/2022 (votação + detalhe) e conferir o zip 2024 e o `municipios.json`.
