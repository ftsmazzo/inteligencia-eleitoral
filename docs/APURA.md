# Apura · Conversa Eleitoral

Painel web com chat analítico sobre dados eleitorais oficiais do Brasil.

**URL pública:** redireciona para `/#demo` (pedido de contato)  
**URL interna (login):** `/apura/app` — não linkada na landing; cadastro público desativado.

## O que é

- Chat humanizado com streaming e indicador “digitando”
- Orquestrador OpenRouter (tools + MCP) + **redator** com voz de especialista em marketing político
- Login, histórico de conversas por usuário
- Exportação **Excel** e **HTML**; relatório HTML **inline** quando o usuário pedir

## Voz do redator

O Apura **não** imita a voz de um candidato. Usa a mesma *estrutura* de guia de voz (essência, tom, caso concreto, oralidade, contraste, checagem) para personificar um **estrategista de marketing político**: firme, oral, de war room — sempre lastreado em `DADOS_OFICIAIS`. Cifra inventada ou biografia fingida = proibido. Prompt em `mcp/apura/prompt.py` (`SYSTEM_WRITER`).

## War room (método)

Skill de sistema `SKILL_WAR_ROOM_DEFAULT` — injetada em **toda** conversa (não gasta as 3 skills do usuário). Ver `docs/SKILL-APURA-WAR-ROOM.md`.

- Pergunta vaga → orquestrador responde `PENDENTE` (máx. 3 recortes) **antes** de chamar tools.
- Redator transforma isso em guia oral + exemplo de pergunta pronta.
- Com dado → fecha com `### Próximo cruzamento`.

Acervo RAG: planos 2026 + **glossário** + **playbooks** + notas TSE + fichas 2018/2022.  
Planos 2018/2022: pipeline `baixar_propostas_governo` + `carregar_propostas_governo` (ver `docs/CARGA-PROPOSTAS-GOVERNO.md`).

## Arquitetura (modelo por função)

Catálogo: `mcp/apura/modelos.py`. Detalhe em `docs/APURA-MULTIAGENTE.md`.

| Papel | Variável | Padrão | Função |
|---|---|---|---|
| **Orquestrador** | `APURA_ORCHESTRATOR_MODEL` | `google/gemini-2.5-flash` | Tools MCP, plano, compactação |
| **Redator** | `APURA_WRITER_MODEL` | `anthropic/claude-sonnet-4.6` | Prosa final (Anthropic) |
| **Ary orch** | `APURA_ARY_ORCHESTRATOR_MODEL` | `google/gemini-2.5-pro` | Modo Ary — roteamento |
| **Ary redator** | `APURA_ARY_WRITER_MODEL` | `anthropic/claude-sonnet-5` | Modo Ary — texto complexo |
| **MCP** | — | — | Postgres `api.*` — **sem IA** |

O redator recebe só a pergunta + dados já consultados (economia de tokens no modelo caro).
Relatório HTML **inline** aparece quando o usuário pedir (ex.: “monte um relatório em HTML”).

**Não** use `openai/gpt-4o` / `gpt-4o-mini` como default de redação — GPT só sob demanda explícita.

## Variáveis de ambiente (EasyPanel · serviço `mcp-api`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENROUTER_API_KEY` | Sim | Chave em [openrouter.ai/keys](https://openrouter.ai/keys) |
| `APURA_JWT_SECRET` | Sim | Segredo para sessões (string longa aleatória) |
| `APURA_MODEL` | Não | Legado; só se orch/writer não forem definidos |
| `APURA_ORCHESTRATOR_MODEL` | Não | Default código: `google/gemini-2.5-flash` — **não** deixe `gpt-4o-mini` no EasyPanel |
| `APURA_WRITER_MODEL` | Não | Default código: `anthropic/claude-sonnet-4.6` — **não** deixe `gpt-4o` no EasyPanel |
| `APURA_ARY_ORCHESTRATOR_MODEL` | Não | Default: `google/gemini-2.5-pro` |
| `APURA_ARY_WRITER_MODEL` | Não | Default: `anthropic/claude-sonnet-5` |
| `APURA_SITE_URL` | Não | URL pública (header OpenRouter) |
| `POSTGRES_ADMIN_URL` | Recomendada | Superusuário Postgres para criar tabelas Apura (DDL) |
| `AGENTE_DATABASE_URL` | Sim | Já usada pelo MCP |
| `MCP_INTERNAL_URL` | Não | Padrão `http://127.0.0.1:8000` |

## DDL

Tabelas criadas automaticamente via `sql/patch_apura.sql`:

- `ctl.apura_usuario`
- `ctl.apura_sessao`
- `ctl.apura_mensagem`
- `ctl.apura_skill` — skills pessoais do redator (até 3 ativas)

Cada usuário Apura recebe um token MCP próprio em `ctl.mcp_token`.

A conversa aberta é restaurada após F5 (id salvo no navegador).

## Skills (painel)

Instruções de tom/formato que o **redator expert** recebe — não alteram fontes de dados.
Até **3 skills ativas** por usuário; cadastro na sidebar “Minhas Skills”.

## API

Prefixo `/apura/api`:

- `POST /auth/registrar` · `POST /auth/login` · `GET /auth/eu`
- `GET /sessoes` · `POST /sessoes` · `PATCH /sessoes/{id}` · `DELETE /sessoes` · `DELETE /sessoes/{id}`
- `GET /sessoes/{id}/mensagens`
- `POST /chat` (SSE)
- `GET /skills` · `POST /skills` · `PATCH /skills/{id}` · `DELETE /skills/{id}`
- `POST /export/xlsx` · `POST /export/html`
