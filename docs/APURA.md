# Apura · Conversa Eleitoral

Painel web com chat analítico sobre dados eleitorais oficiais do Brasil.

**URL:** `/apura` (mesmo host do `mcp-api`)

## O que é

- Chat humanizado com streaming e indicador “digitando”
- Orquestrador OpenRouter (tools + MCP) + **redator expert** em modelo separado
- Login, histórico de conversas por usuário
- Exportação **Excel** e **HTML**; relatório HTML **inline** quando o usuário pedir

## Arquitetura (dois modelos)

| Papel | Variável | Padrão | Função |
|---|---|---|---|
| **Orquestrador** | `APURA_ORCHESTRATOR_MODEL` | `openai/gpt-4o-mini` | Entende a pergunta, chama tools MCP, compacta JSON |
| **Redator** | `APURA_WRITER_MODEL` | `openai/gpt-4o` | Responde ao usuário com tom expert (sem chamar MCP) |
| **MCP** | — | — | Postgres `api.*` — **sem IA** |

O redator recebe só a pergunta + dados já consultados (economia de tokens no modelo caro).
Relatório HTML **inline** aparece quando o usuário pedir (ex.: “monte um relatório em HTML”).

Sugestões OpenRouter para redator: `openai/gpt-4o`, `anthropic/claude-sonnet-4`, `google/gemini-2.5-pro-preview`.

## Variáveis de ambiente (EasyPanel · serviço `mcp-api`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENROUTER_API_KEY` | Sim | Chave em [openrouter.ai/keys](https://openrouter.ai/keys) |
| `APURA_JWT_SECRET` | Sim | Segredo para sessões (string longa aleatória) |
| `APURA_MODEL` | Não | Modelo legado; usado se orchestrator/writer não forem definidos |
| `APURA_ORCHESTRATOR_MODEL` | Não | Modelo barato para tool calling (padrão: `openai/gpt-4o-mini`) |
| `APURA_WRITER_MODEL` | Não | Modelo expert para redação (padrão: `openai/gpt-4o`) |
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
- `GET /sessoes` · `POST /sessoes`
- `GET /sessoes/{id}/mensagens`
- `POST /chat` (SSE)
- `GET /skills` · `POST /skills` · `PATCH /skills/{id}` · `DELETE /skills/{id}`
- `POST /export/xlsx` · `POST /export/html`
