# Parlamento · Câmara e Senado (módulo posterior à urna)

Versão 0.1 · 26/08/2026  
Não mistura com votação TSE. Cifra aqui é **atuação no mandato**, nível oficial das Casas.

## Recorte deste módulo

| Dimensão | Entra | Não entra (ainda) |
|---|---|---|
| Casa | Câmara dos Deputados + Senado Federal | Assembléias estaduais / câmaras municipais |
| Janela | **Legislatura 57** (2023–2027), arquivos anuais **2023–2026** | Séries antigas só se precisarmos de mandato 2019–2022 (L56) — roster L56 baixamos; bulk Câmara pré-2023 fica opcional |
| Âncora urna | Liga a **eleitos 2022** (dep. federal / senador) via de-para | Inventar vínculo por “parece o mesmo nome” sem registrar método |
| Despesa CEAP/cota | Fora do MVP de atuação legislativa | `Ano-AAAA.csv.zip` da cota (inbox) — opcional depois |

`deputados_ne57.json` do `inbox/` **não** é canônico (recorte NE).

## Pacotes canônicos (`data/raw/<id_base>/`)

### Câmara (download em lote oficial)

Base URL: `https://dadosabertos.camara.leg.br/arquivos/`  
Portal: https://dadosabertos.camara.leg.br/

| Id | Arquivo / padrão | Obrigatório MVP |
|---|---|---|
| `br_camara_legislaturas` | `legislaturas/json/legislaturas.json` | sim |
| `br_camara_deputados` | `deputados/json/deputados.json` | sim |
| `br_camara_proposicoes` | `proposicoes/csv/proposicoes-{ano}.csv` · anos 2023–2026 | sim |
| `br_camara_proposicoes_autores` | `proposicoesAutores/csv/proposicoesAutores-{ano}.csv` | sim |
| `br_camara_proposicoes_temas` | `proposicoesTemas/csv/proposicoesTemas-{ano}.csv` | sim |
| `br_camara_votacoes` | `votacoes/csv/votacoes-{ano}.csv` | sim |
| `br_camara_votacoes_votos` | `votacoesVotos/csv/votacoesVotos-{ano}.csv` | sim |
| `br_camara_votacoes_orientacoes` | `votacoesOrientacoes/csv/votacoesOrientacoes-{ano}.csv` | sim |
| `br_camara_votacoes_proposicoes` | `votacoesProposicoes/csv/votacoesProposicoes-{ano}.csv` | sim |

Exemplo completo:  
`https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-2024.csv`

### Senado (API / lista)

Portal: https://www12.senado.leg.br/dados-abertos · API: https://legis.senado.leg.br/dadosabertos/

| Id | URL | Obrigatório MVP |
|---|---|---|
| `br_senado_senadores_atual` | https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json | sim |
| `br_senado_senadores_l56` | https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/56.json | sim (mandato 2019–2023 / urna 2018) |
| `br_senado_senadores_l57` | https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/57.json | sim (mandato 2023–2027 / urna 2022) |
| `br_senado_votacoes_resumo` | https://legis.senado.leg.br/dadosabertos/votacao.json | sim (resumo; ver lacuna abaixo) |

Swagger: https://legis.senado.leg.br/dadosabertos/api-docs/swagger-ui/index.html

## O que NÃO faltou no download

Na rodada automática **todos os arquivos MVP da Câmara (2023–2026) e as listas do Senado (atual, L56, L57) baixaram**.  
O arquivo `parlamento_download_faltas.json` ficou **vazio**.

As “lacunas” abaixo **não são downloads que falharam** — são limites da fonte (o Senado não publica o mesmo tipo de dump anual que a Câmara). A Câmara está completa para o MVP.

## Lacunas honestas (limites da fonte, não inventar)

1. **Votos nominais do Senado em lote completo** — o `votacao.json` é um resumo (centenas de votações), não o espelho dos CSVs da Câmara. Completar depois via:
   - por senador: `https://legis.senado.leg.br/dadosabertos/senador/{codigo}/votacoes.json`
   - catálogo: https://www12.senado.leg.br/dados-abertos/legislativo/plenario/votacoes-nominais/info  
2. **Matérias Senado em dump anual único** — não há `proposicoes-{ano}.csv` equivalente; API sob demanda.  
3. **De-para TSE ↔ id Casa** — tabela preenchida na carga com método `uf+nome_norm` (revisar ambíguos).  
4. **CEAP / cota** — fora do MVP de atuação legislativa.

## O que fazer se o download automático falhar

Copie o arquivo para `data/raw/<id_base>/ano=AAAA/` (ou `estatica/`) como `origem.*` + `origem.sha256` + `meta.json` (mesmo padrão de `data/README.md`).

Links manuais úteis:

- Índice Câmara arquivos: https://dadosabertos.camara.leg.br/swagger/api.html  
- Deputados: https://dadosabertos.camara.leg.br/arquivos/deputados/json/deputados.json  
- Proposições 2025: https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-2025.csv  
- Votos 2025: https://dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/votacoesVotos-2025.csv  
- Senadores L57: https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/57.json  

## Schemas Postgres (alvo)

`parlamentar.*` (não `eleicao.*`):

- `deputado`, `senador` — cadastro Casa  
- `proposicao`, `proposicao_autor`, `proposicao_tema`  
- `votacao`, `voto`, `orientacao`  
- `depara_tse` — `casa`, `id_casa`, `ano_eleicao`, `sq_candidato`, `metodo`, `confianca`

API MCP (fase seguinte à carga): `parlamentar` / `proposicoes` / `votos_parlamentares` — só função nomeada.

## Inbox

Reuso possível: dumps Brasil 2023–2025 em `inbox/camara/` (proposições, autores, votações, votos).  
**Descartar como canônico:** `deputados_ne57.json`.  
Preferência: baixar de novo do portal (SHA controlado) via `scripts/baixar_parlamento.py`.
