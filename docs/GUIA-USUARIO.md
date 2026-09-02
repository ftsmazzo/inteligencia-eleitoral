# Guia do usuÃ¡rio Â· InteligÃªncia Eleitoral Brasil

**Landing (comercial):** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/  
**Pedido de demo:** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/#demo  
**Guia tÃ©cnico (online):** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/guia  
**Apura (interno, sob convite):** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/apura/app

VersÃ£o 2.0 Â· 28/08/2026 â€” este arquivo Ã© espelho estÃ¡tico; prefira a pÃ¡gina web.

Este guia Ã© para **quem usa** a ferramenta â€” nÃ£o para quem administra servidor ou banco de dados.

---

## O que Ã© isto?

Plataforma de **inteligÃªncia eleitoral oficial** do **Brasil inteiro**: urna TSE, contas de campanha, populaÃ§Ã£o IBGE, CadÃšnico, Bolsa FamÃ­lia, CÃ¢mara dos Deputados e camada semÃ¢ntica (planos, fichas territoriais) + radar de clima midiÃ¡tico.

Dois modos de uso:

| Modo | Para quem | Como acessar |
|---|---|---|
| **Apura** | Equipes de campanha, consultoria, imprensa | Acesso sob convite â€” peÃ§a demo na landing |
| **MCP + Skill** | Desenvolvedores e power users | Token sob contato + Cursor, Claude, GPT, Manus |

VocÃª **pergunta em linguagem normal** e a IA consulta a base â€” **sem inventar nÃºmero**.

**NÃ£o Ã©** a ferramenta da campanha NE9. **NÃ£o mistura** achismo com urna.

---

## TrÃªs trilhas de inteligÃªncia

| Trilha | O que entrega | Cifra? |
|---|---|---|
| **A Â· Fato** | Votos, eleitos, contas, populaÃ§Ã£o, social, CÃ¢mara | **Sim** â€” Ãºnica fonte de nÃºmero |
| **B Â· Acervo** | Planos de governo, fichas territoriais, notas TSE | NÃ£o â€” texto Ã© referÃªncia |
| **C Â· Clima** | Google News + Instagram (Radar) | NÃ£o â€” sempre *indÃ­cio* |

O Apura, no **modo narrativa**, estrutura respostas em: **Fato â†’ Programa/acervo â†’ Clima â†’ ImplicaÃ§Ã£o/lacunas**.

---

## O Apura entrega hoje

### Urna e candidatos (Trilha A)

| Consulta | O que faz | Exemplo de pergunta |
|---|---|---|
| VotaÃ§Ã£o | Votos por candidato, partido, UF ou municÃ­pio | â€œVotos do Haddad em SP, gov, 2Âº turno 2022â€ |
| Eleitos | Quem ganhou, por cargo e territÃ³rio | â€œEleitos a senador no Nordeste em 2022â€ |
| Nominata | Quem concorreu (cadastro TSE) | â€œCandidatos PL a dep. federal em PE, 2022â€ |
| Comparecimento | Aptos, comparecimento, brancos, nulos, vÃ¡lidos | â€œApuraÃ§Ã£o em Recife, prefeito 2024â€ |
| Eleitorado | Perfil (sexo, idade, escolaridade) | â€œPerfil do eleitorado de MG em 2022â€ |
| ColigaÃ§Ã£o | ColigaÃ§Ãµes (2014) e federaÃ§Ãµes (2018+) | â€œFederaÃ§Ã£o do PT em SP, gov 2022â€ |
| Vagas | Quantas cadeiras disputadas | â€œVagas de dep. federal em SP, 2022â€ |
| Bens | PatrimÃ´nio declarado ao TSE | â€œPatrimÃ´nio do candidato X em 2022â€ |

### Contas de campanha (Trilha A Â· TSE)

| Consulta | O que faz | Exemplo |
|---|---|---|
| Receita | Financiamento de campanha (maior valor primeiro) | â€œMaiores receitas governador SP 2022â€ |
| Despesa | Gastos de campanha por candidato | â€œDespesas do Haddad em 2022â€ |

**Importante:** despesas/receitas por candidato exigem `sq_candidato` (obtido via votaÃ§Ã£o ou nominata). Candidato eliminado no 1Âº turno tem contas do ano inteiro, mas votos sÃ³ no 1Âº turno.

**Anos carregados hoje:** contas **2014, 2016, 2018, 2020, 2022 e 2024** (federais e municipais no recorte).

### Contexto social e territorial (Trilha A)

| Consulta | Fonte | Exemplo |
|---|---|---|
| PopulaÃ§Ã£o | IBGE | â€œPopulaÃ§Ã£o de Fortaleza no censo 2022â€ |
| CadÃšnico | MDS | â€œFamÃ­lias no CadÃšnico em Recifeâ€ |
| Bolsa FamÃ­lia | MDS | â€œRepasses de Bolsa FamÃ­lia em CEâ€ |

### Parlamento (Trilha A Â· CÃ¢mara)

| Consulta | O que faz |
|---|---|
| Deputados | Quem estÃ¡ na CÃ¢mara agora (mandato L57) |
| Senadores | Senadores em exercÃ­cio |
| ProposiÃ§Ãµes | PLs, PECs etc. por ano e autor |
| Votos CÃ¢mara | Voto nominal de deputado em plenÃ¡rio |
| De-para | Liga urna TSE â†” id CÃ¢mara/Senado |

### AnÃ¡lises compostas (Apura)

| AnÃ¡lise | Ferramentas encadeadas |
|---|---|
| **Gasto vs voto** | VotaÃ§Ã£o â†’ sq_candidato â†’ receita + despesa |
| **EvoluÃ§Ã£o partidÃ¡ria** | Linha temporal de eleitos (ex.: PL dep. federal Nordeste 2014â†’2022) |
| **Social Ã— urna** | CadÃšnico/Bolsa cruzado com eleito por municÃ­pio |
| **Mandato Ã— urna** | Deputado na CÃ¢mara + proposiÃ§Ãµes + origem na urna 2022 |
| **Deputado: como votou** | Deputados â†’ votos nominais na CÃ¢mara |
| **Narrativa de campanha** | Fato + acervo (plano) + clima (notÃ­cias) |

### Acervo semÃ¢ntico (Trilha B)

| Tipo | Status | Uso |
|---|---|---|
| Planos de governo **2026** | Carregado | â€œO que o candidato X promete sobre seguranÃ§a?â€ |
| Planos 2018/2022 | Lacuna (em expansÃ£o) | Apura informa explicitamente quando nÃ£o hÃ¡ |
| Fichas territoriais | Derivadas da urna | Perfil eleitoral por UF |
| Notas TSE | Sob demanda | ColigaÃ§Ã£o vs federaÃ§Ã£o, regras do ciclo |
| Comparador | Ativo | Mesmo tema em dois anos (ex.: 2022 vs 2026) |

### Clima / Radar (Trilha C)

- **Google News** â€” Ãºltimas 24h ou 168h por tema ou pessoa
- **Instagram** â€” menÃ§Ãµes por handle (Apify)
- Sempre rotulado como **indÃ­cio** â€” nunca substitui urna

### ExportaÃ§Ã£o (Apura)

- **RelatÃ³rio HTML** â€” peÃ§a â€œexporte em HTMLâ€ ou â€œmonte um relatÃ³rioâ€
- **Planilha XLSX** â€” botÃ£o exportar na conversa
- SessÃµes salvas, fixar conversa, histÃ³rico por usuÃ¡rio

---

## Anos disponÃ­veis

| Tipo | Anos com urna | Contas TSE |
|---|---|---|
| Presidente, gov, senador, deputados | **2014, 2018, 2022** | 2018, 2022 (hoje) |
| Prefeito e vereador | **2016, 2020, 2024** | em expansÃ£o |
| Candidaturas 2026 | SÃ³ **cadastro** â€” sem votos atÃ© apuraÃ§Ã£o | â€” |

### O que **nÃ£o** dÃ¡ para perguntar

- EleiÃ§Ãµes antes de 2014 ou fora do recorte
- Resultado de **2026** antes da apuraÃ§Ã£o oficial
- Estimativas ou completar lacuna com outra regiÃ£o
- Pesquisa eleitoral de instituto (nÃ£o Ã© urna)
- NÃºmero vindo sÃ³ de notÃ­cia ou plano de governo

Lista vazia = **inexistente**, nÃ£o zero.

---

## Passo 1 Â· Acesso

### Apura (recomendado para equipes)

1. PeÃ§a acesso em https://â€¦/#demo (formulÃ¡rio ou WhatsApp)
2. A equipe libera login
3. Entre em `/apura/app` com o e-mail/senha fornecidos
4. Ative **modo narrativa** quando quiser Fato + Programa + Clima
5. Pergunte com **ano + cargo + lugar**

Cadastro pÃºblico estÃ¡ **desativado**.

### MCP (desenvolvedores e IAs)

Quem administra passa um **token secreto** ou vocÃª gera em `/guia` â†’ â€œGerar tokenâ€.

Guarde em local seguro. **NÃ£o** publique nem commite no git.

---

## Passo 2 Â· Conectar na sua IA

### OpÃ§Ã£o A Â· Cursor (recomendado)

Settings â†’ MCP â†’ cole:

```json
{
  "mcpServers": {
    "inteligencia-eleitoral-brasil": {
      "url": "https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp",
      "headers": {
        "Authorization": "Bearer SEU_TOKEN_AQUI"
      }
    }
  }
}
```

Arquivo pronto: `docs/config/mcp-cursor.json` ou download em `/guia`.

### OpÃ§Ã£o B Â· Claude Desktop

Mesmo JSON em `docs/config/mcp-claude.json`.

### OpÃ§Ã£o C Â· ChatGPT, Manus ou IA sem MCP

1. Copie `docs/SKILL-INTELIGENCIA-ELEITORAL.md`
2. Cole nas instruÃ§Ãµes do agente
3. Informe URL MCP + token (sÃ³ na configuraÃ§Ã£o)

### OpÃ§Ã£o D Â· Teste REST

```
POST https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp
Authorization: Bearer SEU_TOKEN_AQUI
Content-Type: application/json

{"method": "catalogo", "params": {}}
```

---

## Passo 3 Â· Boas perguntas

1. **Ano** (2022, 2024â€¦)
2. **Cargo** (presidente, governador, senador, deputado_federal, deputado_estadual, prefeito, vereador)
3. **Onde** â€” UF (`SP`, `PE`) ou municÃ­pio (IBGE 7 dÃ­gitos)
4. **Turno** â€” quando for 2Âº turno, diga explicitamente
5. **Quem** â€” partido, nome de urna ou nÃºmero

**Bom:** â€œCompare despesas e votos de Haddad e TarcÃ­sio, gov SP, 2Âº turno 2022.â€  
**Ruim:** â€œComo foi a eleiÃ§Ã£o?â€

### RegiÃµes e partidos

- **RegiÃ£o:** â€œNordesteâ€, â€œSudesteâ€ â€” a base expande UFs
- **Partido:** sigla atual (PL, MDB) â€” expande histÃ³rico (PLâ†”PSL, MDBâ†”PMDB)

---

## Passo 4 Â· Entender a resposta

- **`status: ok`** â€” encontrou dados
- **`status: vazio`** â€” consulta ok, sem linhas (repita com sq_candidato ou turno)
- **`status: fora_do_recorte`** â€” pedido invÃ¡lido
- Lista vazia â‰  zero votos

Percentual: peÃ§a â€œsobre votos **vÃ¡lidos**â€ ou use `base_pct: "validos"`.

---

## Passo 5 Â· Skill para IA

**`docs/SKILL-INTELIGENCIA-ELEITORAL.md`** â€” download em `/guia`.

No Cursor: `.cursor/skills/inteligencia-eleitoral-brasil/`.

---

## Roadmap (em breve)

| Item | DescriÃ§Ã£o |
|---|---|
| Acervo 2018/2022 | Planos de governo dos ciclos anteriores |
| Contas 2014â€“2024 | PrestaÃ§Ã£o TSE completa no recorte |
| Totais agregados | `consultar_contas_resumo` / `api.contas_resumo` â€” receita, despesa, categorias e custo/voto |
| Radar por campanha | Clima dedicado por `campaign_id` |
| API white-label | Embeddable para portais de clientes |

---

## Checklist

- [ ] Acesso Apura ou token MCP
- [ ] Skill instalada (se usar IA externa)
- [ ] Testei com pergunta simples (ano + cargo + UF)
- [ ] Sei que 2026 ainda nÃ£o tem urna
- [ ] Sei que vazio = inexistente, nÃ£o zero

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| â€œnÃ£o autorizadoâ€ | Token errado ou login Apura invÃ¡lido |
| â€œfora do recorteâ€ | Ano/cargo/territÃ³rio fora da tabela |
| Despesa vazia com candidato conhecido | PeÃ§a comparar com sq_candidato ou turno correto |
| IA inventa nÃºmero | Reforce: â€œsÃ³ InteligÃªncia Eleitoral, sem estimarâ€ |

**Health:** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/health â†’ `{"status":"ok"}`

---

## Onde saber mais

| Documento | Para quem |
|---|---|
| `/` (landing) | ApresentaÃ§Ã£o comercial |
| `docs/SKILL-INTELIGENCIA-ELEITORAL.md` | IA / agentes |
| `docs/ENTREGA-MCP.md` | Equipe tÃ©cnica |
| `docs/ACERVO.md` | Acervo e Radar |
| `docs/SPEC-BRASIL.md` | Recorte oficial |

---

## Resumo

**Apura para conversa Â· MCP para integraÃ§Ã£o Â· Skill para comportamento correto Â· SÃ³ nÃºmeros da base oficial.**
