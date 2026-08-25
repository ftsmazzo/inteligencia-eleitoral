# Spec · Inteligência Eleitoral Brasil

Versão 0.1 · 25/08/2026  
Não é a spec da campanha NE9. O pacote em `Arquitetura/` é arquivo histórico.

## Recorte da ferramenta

| Dimensão | O que entra | O que não entra |
|---|---|---|
| Território | Brasil (27 UF + DF), município IBGE 7 dígitos | Default Nordeste; rateio UF→município |
| Cargos | Presidente, governador, senador, deputado federal, deputado estadual, prefeito, vereador | Cargo ou urna fora da lista |
| Urnas federais/estaduais | **2014, 2018, 2022** (resultado) + **2026** (candidatura viva; resultado só depois da urna) | 2002–2012; resultado 2026 antes da apuração oficial |
| Urnas municipais | **2016, 2020, 2024** | 2012 e anteriores; 2028 (ainda não ocorreu) |
| Número | Trilha A relacional | Embedding de cifra |
| Texto / clipping | Trilha B ou MCP irmão, nível `indicio` | Cifra extraída de notícia como fato |

Quebra obrigatória no metadado: coligação proporcional em **2014** ≠ regra **2018+**. Percentual: coluna `base_pct` = `validos` ou `soma_dois`, nunca misturar.

## Resposta fora do recorte (seca)

Se a pergunta pedir ano, cargo, território ou indicador fora da tabela acima, o agente **não estima, não aproxima, não completa com campanha NE9**. Devolve só:

> Fora do recorte. O escopo da solicitação não faz parte do recorte desta ferramenta, que é: Brasil; cargos de presidente a vereador; eleições federais/estaduais 2014, 2018 e 2022 (resultado) e 2026 (candidatura, resultado após a urna); eleições municipais 2016, 2020 e 2024. Pedido: [resumir o que pediram]. Dado inexistente neste recorte.

Sem parágrafo de contexto, sem “mas se considerarmos…”, sem puxar 2010 ou só o Nordeste.

## Duas trilhas

- **A:** célula de planilha → PostgreSQL, função nomeada, conjunto vazio = inexistente.
- **B:** parágrafo → pgvector / acervo. Número no texto da B é pista, não fato.

## Pastas de dado (uma árvore, sem colcha)

`Arquitetura/` não recebe arquivo novo.  
`inbox/` = despejo sujo, só leitura.  
`data/` = canônico (`data/README.md`). Raw imutável → staging Parquet → Postgres.

## Catálogo deste produto

Fonte da verdade futura: `docs/catalogo_nucleo.json` (a criar na carga).  
Links oficiais agora: `docs/FONTES-NUCLEO.md`.  
O `Arquitetura/catalogo_bases.json` (100/105 bases da chapa) **não** é o backlog deste repositório.
