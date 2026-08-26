# Apura · Conversa Eleitoral

Painel web com chat analítico sobre dados eleitorais oficiais do Brasil.

**URL:** `/apura` (mesmo host do `mcp-api`)

## O que é

- Chat humanizado com streaming e indicador “digitando”
- Orquestrador OpenRouter + consultas MCP (números nunca inventados)
- Login, histórico de conversas por usuário
- Exportação **Excel** e **HTML** quando a resposta inclui dados tabulares

## Variáveis de ambiente (EasyPanel · serviço `mcp-api`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENROUTER_API_KEY` | Sim | Chave em [openrouter.ai/keys](https://openrouter.ai/keys) |
| `APURA_JWT_SECRET` | Sim | Segredo para sessões (string longa aleatória) |
| `APURA_MODEL` | Não | Modelo OpenRouter (padrão: `openai/gpt-4o-mini`) |
| `APURA_SITE_URL` | Não | URL pública (header OpenRouter) |
| `POSTGRES_ADMIN_URL` | Recomendada | Superusuário Postgres para criar tabelas Apura (DDL) |
| `AGENTE_DATABASE_URL` | Sim | Já usada pelo MCP |
| `MCP_INTERNAL_URL` | Não | Padrão `http://127.0.0.1:8000` |

## DDL

Tabelas criadas automaticamente via `sql/patch_apura.sql`:

- `ctl.apura_usuario`
- `ctl.apura_sessao`
- `ctl.apura_mensagem`

Cada usuário Apura recebe um token MCP próprio em `ctl.mcp_token`.

## API

Prefixo `/apura/api`:

- `POST /auth/registrar` · `POST /auth/login` · `GET /auth/eu`
- `GET /sessoes` · `POST /sessoes`
- `GET /sessoes/{id}/mensagens`
- `POST /chat` (SSE)
- `POST /export/xlsx` · `POST /export/html`
