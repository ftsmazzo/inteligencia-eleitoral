# Contrato · Plataforma Gestão (multi-campanha + Perfis)

Versão 0.2 · 05/09/2026  
Status: **P0–P5** (schema, APIs, shell multi-tenant, Perfil, auditoria, quotas). Redesign do Chat = conversa seguinte.  
Classificação das tabelas novas: **interno** (ctl.* de produto). Tokens/e-mails: **sensível** — nunca commitar valores reais.

## 1. Problema que este contrato resolve

Hoje a Gestão é um wizard **dentro** da campanha do login. Chat, Radar, Clima e MCP já herdam `campanha_id` do cookie/JWT. Modelo e tools são globais (env + `MCP_TOOLS`).

Destino: **shell de plataforma** (super gestor) separado do **workspace** (tools da campanha). Frota, dash, quotas e logs na plataforma; Chat/Radar/Skills só depois de **Operar**. Política de IA/tools = **Perfil no vínculo** (usuário × campanha).

## 2. Papéis

| Papel | Quem | Poder |
|---|---|---|
| **Super gestor** | Exatamente 3: Frederico Mazzo (`fredmazzo@gmail.com`), Leonardo Tamburus (`leonardotamburus@gmail.com`), Ary Engracia (`aryengracia@gmail.com`) | Shell plataforma (dash, frota, quotas, conversas, eventos); criar campanha; CRUD de Perfis; tokens MCP; **Operar** ou **Administrar** por campanha |
| **Coordenador** | Membro com `papel_campanha=coordenador` | Gestão **daquela** campanha: escopo, motor, dossiê, seed Radar, liberar equipe, convidar membros e atribuir Perfil |
| **Equipe** | Membro com `papel_campanha=equipe` | Usa módulos liberados da campanha ativa, sob o Perfil do vínculo |

Super gestores são identificados por e-mail em `ctl.plataforma_super_gestor` (seed fechado).

Não existe “dono de conta” de cliente acima dos três.

## 3. Navegação e contexto

| Rota (alvo) | Quem | Contexto |
|---|---|---|
| Shell plataforma | Super gestores | Sem tools na sidebar; `campanha_ativa` limpa no login; abas Visão geral · Frota · Quotas · Conversas · Eventos |
| **Operar** campanha | Super | `POST /entrar` → workspace com Chat/Radar/Gestão-da-campanha + Skills |
| **Administrar** campanha | Super | Filtro `adminCampanhaId` no shell (não vira usuário de chat) |
| **Voltar à plataforma** | Super no workspace | `POST /sair` + shell limpo |
| Seletor pós-login | Quem tem N vínculos (não-super) | Escolhe campanha → grava `campanha_ativa_id` |
| Workspace (`/apura/app`) | Membro com campanha ativa | Chat / Radar / Clima / Gestão-da-campanha herdam o id |
| 1 vínculo só | Equipe/coordenador | Entra direto, sem seletor |

Sem campanha ativa: Chat, Radar e Clima **indisponíveis**.  
Criar campanha **não** coloca o gestor “dentro” dela — usa **Operar**.

## 4. Hierarquia de dados

```
Plataforma (3 super gestores)
  └─ Perfis (templates: modelos + tools + limites)
  └─ Campanhas
        ├─ Módulos provisionados na criação (virgens)
        ├─ quota_perguntas_max (agregado opcional)
        ├─ Escopo / memória / Radar (configuração posterior)
        ├─ Membros: (usuario + perfil + papel_campanha)
        └─ Tokens MCP: (campanha + perfil + rótulo)
```

- **Campanha** define *quais módulos existem* e cota agregada opcional.
- **Perfil** define *modelo orquestrador, modelo redator, tools permitidas, quotas*.
- **Vínculo** (`campanha_membro`) amarra usuário × campanha × Perfil.

## 5. Módulos na criação da campanha

Ao `POST` criar campanha, provisionar linhas em `ctl.campanha_modulo` (ativas, vazias/virgens):

| codigo | Descrição |
|---|---|
| `chat` | Apura conversacional |
| `radar` | Alvos / termômetro |
| `clima` | Tool `consultar_clima` + ingestão futura |
| `dados_mcp` | Superfície MCP/REST no contexto da campanha |
| `gestao_campanha` | Wizard de escopo/motor/dossiê/liberar (só coordenador+) |

## 6. Perfis seed (editáveis pelos 3)

| slug | Modelos (default OpenRouter) | Tools (resumo) |
|---|---|---|
| `consultor_minimo` | orch + writer baratos | catalogo, municipio, nominata |
| `analista` | orch médio / writer forte | + cifras TSE, social, contas, Parlamento, população/MDS, cruzamentos |
| `estrategista` | orch + writer fortes | Analista + acervo + clima |
| `coordenador` | iguais ao estrategista | Mesmas tools; poder extra é UI/API de gestão da campanha |

Enforcement: filtrar `MCP_TOOLS` no orchestrator **e** rejeitar tool call fora da allowlist no servidor.

## 7. MCP externo (times que consomem dados)

| Canal | Autenticação | Matriz |
|---|---|---|
| Apura UI | JWT + `campanha_ativa` + Perfil do vínculo | Fina |
| MCP / REST de campanha | `ctl.mcp_token` com `campanha_id` + `perfil_id` | **Mesma** matriz do Perfil |
| Token mestre (`MCP_TOKEN` env) | Só Fábrica / automação dos 3 | Bypass — **nunca** distribuir |

## 8. Auditoria, quotas e IA (só super gestores)

- `ctl.evento_acesso`: login, logout, troca de campanha, CRUD, quotas, etc.
- Conversas: `ctl.apura_sessao` / `apura_mensagem` com drill-down read-only.
- Quotas: usuário + `ctl.campanha.quota_perguntas_max`; enforcement no chat.
- IA de governança: `POST /auditoria/sugerir` — sem cifras eleitorais inventadas.

## 9. Migração do estado atual

1. Manter `ctl.apura_usuario.campanha_id` como legado até backfill.
2. Backfill `campanha_membro` + `campanha_ativa_id`.
3. Provisionar módulos nas campanhas existentes.
4. Super no login: `POST /sair` + shell plataforma (não herdar campanha residual).

## 10. Fora de escopo desta fatia

- Redesign do Chat.
- Gateway de pagamento (Stripe etc.).
- RAG de clima / Apify.
- Alterar SPEC-BRASIL ou `api.*`.

## 11. Artefatos

| Artefato | Caminho |
|---|---|
| Este contrato | `docs/CONTRATO-PLATAFORMA-GESTAO.md` |
| Patch runtime | `sql/patch_gestao_v3.sql` + `sql/patch_gestao_v4.sql` |
| Store + API | `plataforma.py`, `routes_plataforma.py`, `auditoria.py` |
