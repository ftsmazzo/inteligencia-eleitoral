# Guia do usuário · Inteligência Eleitoral Brasil

**Landing (comercial):** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/  
**Pedido de demo:** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/#demo  
**Guia técnico (online):** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/guia  
**Apura (interno, sob convite):** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/apura/app

Versão 2.0 · 28/08/2026 — este arquivo é espelho estático; prefira a página web.

Este guia é para **quem usa** a ferramenta — não para quem administra servidor ou banco de dados.

---

## O que é isto?

Plataforma de **inteligência eleitoral oficial** do **Brasil inteiro**: urna TSE, contas de campanha, população IBGE, CadÚnico, Bolsa Família, Câmara dos Deputados e camada semântica (planos, fichas territoriais) + radar de clima midiático.

Dois modos de uso:

| Modo | Para quem | Como acessar |
|---|---|---|
| **Apura** | Equipes de campanha, consultoria, imprensa | Acesso sob convite — peça demo na landing |
| **MCP + Skill** | Desenvolvedores e power users | Token sob contato + Cursor, Claude, GPT, Manus |

Você **pergunta em linguagem normal** e a IA consulta a base — **sem inventar número**.

**Não é** a ferramenta da campanha NE9. **Não mistura** achismo com urna.

---

## Três trilhas de inteligência

| Trilha | O que entrega | Cifra? |
|---|---|---|
| **A · Fato** | Votos, eleitos, contas, população, social, Câmara | **Sim** — única fonte de número |
| **B · Acervo** | Planos de governo, fichas territoriais, notas TSE | Não — texto é referência |
| **C · Clima** | Google News + Instagram (Radar) | Não — sempre *indício* |

O Apura, no **modo narrativa**, estrutura respostas em: **Fato → Programa/acervo → Clima → Implicação/lacunas**.

---

## O Apura entrega hoje

### Urna e candidatos (Trilha A)

| Consulta | O que faz | Exemplo de pergunta |
|---|---|---|
| Votação | Votos por candidato, partido, UF ou município | “Votos do Haddad em SP, gov, 2º turno 2022” |
| Eleitos | Quem ganhou, por cargo e território | “Eleitos a senador no Nordeste em 2022” |
| Nominata | Quem concorreu (cadastro TSE) | “Candidatos PL a dep. federal em PE, 2022” |
| Comparecimento | Aptos, comparecimento, brancos, nulos, válidos | “Apuração em Recife, prefeito 2024” |
| Eleitorado | Perfil (sexo, idade, escolaridade) | “Perfil do eleitorado de MG em 2022” |
| Coligação | Coligações (2014) e federações (2018+) | “Federação do PT em SP, gov 2022” |
| Vagas | Quantas cadeiras disputadas | “Vagas de dep. federal em SP, 2022” |
| Bens | Patrimônio declarado ao TSE | “Patrimônio do candidato X em 2022” |

### Contas de campanha (Trilha A · TSE)

| Consulta | O que faz | Exemplo |
|---|---|---|
| Receita | Financiamento de campanha (maior valor primeiro) | “Maiores receitas governador SP 2022” |
| Despesa | Gastos de campanha por candidato | “Despesas do Haddad em 2022” |

**Importante:** despesas/receitas por candidato exigem `sq_candidato` (obtido via votação ou nominata). Candidato eliminado no 1º turno tem contas do ano inteiro, mas votos só no 1º turno.

**Anos carregados hoje:** contas **2014, 2016, 2018, 2020, 2022 e 2024** (federais e municipais no recorte).

### Contexto social e territorial (Trilha A)

| Consulta | Fonte | Exemplo |
|---|---|---|
| População | IBGE | “População de Fortaleza no censo 2022” |
| CadÚnico | MDS | “Famílias no CadÚnico em Recife” |
| Bolsa Família | MDS | “Repasses de Bolsa Família em CE” |

### Parlamento (Trilha A · Câmara)

| Consulta | O que faz |
|---|---|
| Deputados | Quem está na Câmara agora (mandato L57) |
| Senadores | Senadores em exercício |
| Proposições | PLs, PECs etc. por ano e autor |
| Votos Câmara | Voto nominal de deputado em plenário |
| De-para | Liga urna TSE ↔ id Câmara/Senado |

### Análises compostas (Apura)

| Análise | Ferramentas encadeadas |
|---|---|
| **Gasto vs voto** | Votação → sq_candidato → receita + despesa |
| **Evolução partidária** | Linha temporal de eleitos (ex.: PL dep. federal Nordeste 2014→2022) |
| **Social × urna** | CadÚnico/Bolsa cruzado com eleito por município |
| **Mandato × urna** | Deputado na Câmara + proposições + origem na urna 2022 |
| **Deputado: como votou** | Deputados → votos nominais na Câmara |
| **Narrativa de campanha** | Fato + acervo (plano) + clima (notícias) |

### Acervo semântico (Trilha B)

| Tipo | Status | Uso |
|---|---|---|
| Planos de governo **2026** | Carregado | “O que o candidato X promete sobre segurança?” |
| Planos 2018/2022 | Lacuna (em expansão) | Apura informa explicitamente quando não há |
| Fichas territoriais | Derivadas da urna | Perfil eleitoral por UF |
| Notas TSE | Sob demanda | Coligação vs federação, regras do ciclo |
| Comparador | Ativo | Mesmo tema em dois anos (ex.: 2022 vs 2026) |

### Clima / Radar (Trilha C)

- **Google News** — últimas 24h ou 168h por tema ou pessoa
- **Instagram** — menções por handle (Apify)
- Sempre rotulado como **indício** — nunca substitui urna

### Exportação (Apura)

- **Relatório HTML** — peça “exporte em HTML” ou “monte um relatório”
- **Planilha XLSX** — botão exportar na conversa
- Sessões salvas, fixar conversa, histórico por usuário

---

## Anos disponíveis

| Tipo | Anos com urna | Contas TSE |
|---|---|---|
| Presidente, gov, senador, deputados | **2014, 2018, 2022** | 2018, 2022 (hoje) |
| Prefeito e vereador | **2016, 2020, 2024** | em expansão |
| Candidaturas 2026 | Só **cadastro** — sem votos até apuração | — |

### O que **não** dá para perguntar

- Eleições antes de 2014 ou fora do recorte
- Resultado de **2026** antes da apuração oficial
- Estimativas ou completar lacuna com outra região
- Pesquisa eleitoral de instituto (não é urna)
- Número vindo só de notícia ou plano de governo

Lista vazia = **inexistente**, não zero.

---

## Passo 1 · Acesso

### Apura (recomendado para equipes)

1. Peça acesso em https://…/#demo (formulário ou WhatsApp)
2. A equipe libera login
3. Entre em `/apura/app` com o e-mail/senha fornecidos
4. Ative **modo narrativa** quando quiser Fato + Programa + Clima
5. Pergunte com **ano + cargo + lugar**

Cadastro público está **desativado**.

### MCP (desenvolvedores e IAs)

Quem administra passa um **token secreto** ou você gera em `/guia` → “Gerar token”.

Guarde em local seguro. **Não** publique nem commite no git.

---

## Passo 2 · Conectar na sua IA

### Opção A · Cursor (recomendado)

Settings → MCP → cole:

```json
{
  "mcpServers": {
    "inteligencia-eleitoral-brasil": {
      "url": "https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp",
      "headers": {
        "Authorization": "Bearer SEU_TOKEN_AQUI"
      }
    }
  }
}
```

Arquivo pronto: `docs/config/mcp-cursor.json` ou download em `/guia`.

### Opção B · Claude Desktop

Mesmo JSON em `docs/config/mcp-claude.json`.

### Opção C · ChatGPT, Manus ou IA sem MCP

1. Copie `docs/SKILL-INTELIGENCIA-ELEITORAL.md`
2. Cole nas instruções do agente
3. Informe URL MCP + token (só na configuração)

### Opção D · Teste REST

```
POST https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp
Authorization: Bearer SEU_TOKEN_AQUI
Content-Type: application/json

{"method": "catalogo", "params": {}}
```

---

## Passo 3 · Boas perguntas

1. **Ano** (2022, 2024…)
2. **Cargo** (presidente, governador, senador, deputado_federal, deputado_estadual, prefeito, vereador)
3. **Onde** — UF (`SP`, `PE`) ou município (IBGE 7 dígitos)
4. **Turno** — quando for 2º turno, diga explicitamente
5. **Quem** — partido, nome de urna ou número

**Bom:** “Compare despesas e votos de Haddad e Tarcísio, gov SP, 2º turno 2022.”  
**Ruim:** “Como foi a eleição?”

### Regiões e partidos

- **Região:** “Nordeste”, “Sudeste” — a base expande UFs
- **Partido:** sigla atual (PL, MDB) — expande histórico (PL↔PSL, MDB↔PMDB)

---

## Passo 4 · Entender a resposta

- **`status: ok`** — encontrou dados
- **`status: vazio`** — consulta ok, sem linhas (repita com sq_candidato ou turno)
- **`status: fora_do_recorte`** — pedido inválido
- Lista vazia ≠ zero votos

Percentual: peça “sobre votos **válidos**” ou use `base_pct: "validos"`.

---

## Passo 5 · Skill para IA

**`docs/SKILL-INTELIGENCIA-ELEITORAL.md`** — download em `/guia`.

No Cursor: `.cursor/skills/inteligencia-eleitoral-brasil/`.

---

## Roadmap (em breve)

| Item | Descrição |
|---|---|
| Acervo 2018/2022 | Planos de governo dos ciclos anteriores |
| Contas 2014–2024 | Prestação TSE completa no recorte |
| Totais agregados | Soma receita/despesa por candidato em uma consulta |
| Radar por campanha | Clima dedicado por `campaign_id` |
| API white-label | Embeddable para portais de clientes |

---

## Checklist

- [ ] Acesso Apura ou token MCP
- [ ] Skill instalada (se usar IA externa)
- [ ] Testei com pergunta simples (ano + cargo + UF)
- [ ] Sei que 2026 ainda não tem urna
- [ ] Sei que vazio = inexistente, não zero

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| “não autorizado” | Token errado ou login Apura inválido |
| “fora do recorte” | Ano/cargo/território fora da tabela |
| Despesa vazia com candidato conhecido | Peça comparar com sq_candidato ou turno correto |
| IA inventa número | Reforce: “só Inteligência Eleitoral, sem estimar” |

**Health:** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/health → `{"status":"ok"}`

---

## Onde saber mais

| Documento | Para quem |
|---|---|
| `/` (landing) | Apresentação comercial |
| `docs/SKILL-INTELIGENCIA-ELEITORAL.md` | IA / agentes |
| `docs/ENTREGA-MCP.md` | Equipe técnica |
| `docs/ACERVO.md` | Acervo e Radar |
| `docs/SPEC-BRASIL.md` | Recorte oficial |

---

## Resumo

**Apura para conversa · MCP para integração · Skill para comportamento correto · Só números da base oficial.**
