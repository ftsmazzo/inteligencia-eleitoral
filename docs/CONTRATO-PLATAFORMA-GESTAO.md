# Contrato · Plataforma Gestão (multi-campanha + Perfis)

Versão 0.1 · 04/09/2026  
Status: **P0–P4 feitos** (schema, APIs, UI, Perfil, auditoria/IA). Redesign do Chat = conversa seguinte.  
Classificação das tabelas novas: **interno** (ctl.* de produto). Tokens/e-mails: **sensível** — nunca commitar valores reais.

## 1. Problema que este contrato resolve

Hoje a Gestão é um wizard **dentro** da campanha do login. Chat, Radar, Clima e MCP já herdam `campanha_id` do cookie/JWT. Modelo e tools são globais (env + `MCP_TOOLS`).

Destino: shell de **plataforma** → criar/listar campanhas → **entrar** → ferramentas nascem virgens e só então recebem contexto. Política de IA/tools = **Perfil no vínculo** (usuário × campanha).

## 2. Papéis

| Papel | Quem | Poder |
|---|---|---|
| **Super gestor** | Exatamente 3: Frederico Mazzo (`fredmazzo@gmail.com`), Leonardo Tamburus (`leonardotamburus@gmail.com`), Ary Engracia (`aryengracia@gmail.com`) | Frota de todas as campanhas; criar campanha; CRUD de Perfis da plataforma; emitir tokens MCP de campanha; ver auditoria global + IA de boas práticas; tudo passa por eles |
| **Coordenador** | Membro com `papel_campanha=coordenador` | Gestão **daquela** campanha: escopo, motor, dossiê, seed Radar, liberar equipe, convidar membros e atribuir Perfil |
| **Equipe** | Membro com `papel_campanha=equipe` | Usa módulos liberados da campanha ativa, sob o Perfil do vínculo |

Super gestores são identificados por e-mail em `ctl.plataforma_super_gestor` (seed fechado).

Não existe “dono de conta” de cliente acima dos três.

## 3. Navegação e contexto

| Rota (alvo) | Quem | Contexto |
|---|---|---|
| Shell Gestão (frota) | Super gestores | Sem `campanha_ativa` — visão de todas |
| Seletor pós-login | Quem tem N vínculos | Escolhe campanha → grava `campanha_ativa_id` |
| Workspace (`/apura/app`) | Membro com campanha ativa | Chat / Radar / Clima / Gestão-da-campanha herdam o id |
| 1 vínculo só | Equipe/coordenador | Entra direto, sem seletor |

Sem campanha ativa: Chat, Radar e Clima **indisponíveis** (não “legado vazio”).  
Criar campanha **não** coloca o gestor “dentro” dela automaticamente — ele escolhe **Entrar**.

## 4. Hierarquia de dados

```
Plataforma (3 super gestores)
  └─ Perfis (templates: modelos + tools + limites)
  └─ Campanhas
        ├─ Módulos provisionados na criação (virgens)
        ├─ Escopo / memória / Radar (configuração posterior)
        ├─ Membros: (usuario + perfil + papel_campanha)
        └─ Tokens MCP: (campanha + perfil + rótulo)
```

- **Campanha** define *quais módulos existem* (chat, radar, clima, dados_mcp, …).
- **Perfil** define *modelo orquestrador, modelo redator, tools permitidas, quotas*.
- **Vínculo** (`campanha_membro`) amarra João + Campanha A + “Consultor mínimo” e João + Campanha B + “Analista”.

## 5. Módulos na criação da campanha

Ao `POST` criar campanha, provisionar linhas em `ctl.campanha_modulo` (ativas, vazias/virgens):

| codigo | Descrição |
|---|---|
| `chat` | Apura conversacional |
| `radar` | Alvos / termômetro |
| `clima` | Tool `consultar_clima` + ingestão futura |
| `dados_mcp` | Superfície MCP/REST no contexto da campanha |
| `gestao_campanha` | Wizard de escopo/motor/dossiê/liberar (só coordenador+) |

Módulos futuros = novas linhas no catálogo + default na criação. Desligar módulo = `ativo=false` (UI esconde; API rejeita).

## 6. Perfis seed (editáveis pelos 3)

| slug | Modelos (default OpenRouter) | Tools (resumo) |
|---|---|---|
| `consultor_minimo` | orch + writer baratos | catalogo, municipio, nominata |
| `analista` | orch médio / writer forte | + cifras TSE, social, contas, Parlamento, população/MDS, cruzamentos |
| `estrategista` | orch + writer fortes | Analista + acervo + clima |
| `coordenador` | iguais ao estrategista | Mesmas tools; poder extra é UI/API de gestão da campanha |

Defaults de modelo (ajustáveis na tabela):

- Barato: `openai/gpt-4o-mini` (orch e/ou writer)
- Forte: orch `anthropic/claude-sonnet-4` · writer `openai/gpt-4o`  
  (espelham o padrão atual de env; trocar sem deploy de código)

Enforcement: filtrar `MCP_TOOLS` no orchestrator **e** rejeitar tool call fora da allowlist no servidor. Logar modelo + tools em `dados_json` / eventos.

## 7. MCP externo (times que consomem dados)

| Canal | Autenticação | Matriz |
|---|---|---|
| Apura UI | JWT + `campanha_ativa` + Perfil do vínculo | Fina |
| MCP / REST de campanha | `ctl.mcp_token` com `campanha_id` + `perfil_id` | **Mesma** matriz do Perfil |
| Token mestre (`MCP_TOKEN` env) | Só Fábrica / automação dos 3 | Bypass — **nunca** distribuir |

Times parceiros recebem token emitido na Gestão da campanha (rótulo + Perfil). Operam já no `campanha_id` do token. Quota e log por token.

## 8. Auditoria e IA de boas práticas (só super gestores)

- `ctl.evento_acesso`: login, logout, troca de campanha, CRUD membro/perfil, emitir token, liberar equipe, seed radar, upload dossiê, etc.
- Interações Apura: já em `ctl.apura_mensagem` (+ `dados_json` com tools); painel agrega por usuário/campanha.
- **IA de governança** (fase posterior ao schema): só os 3; lê agregados operacionais; sugere boas práticas de uso; **nunca** inventa cifra eleitoral (Trilha A continua só via tools oficiais).

## 9. Migração do estado atual

1. Manter `ctl.apura_usuario.campanha_id` como legado de leitura até backfill.
2. Para cada usuário com `campanha_id`, criar `campanha_membro` com perfil `estrategista` se `papel=coordenador`, senão `analista` (ajustável).
3. `campanha_ativa_id` ← `campanha_id` atual.
4. Campanhas existentes (`governador-amapa`, `alfredo-gaspar`, …): provisionar módulos se faltarem.
5. Tokens MCP existentes: preencher `perfil_id` default `analista` quando tiverem `campanha_id`.
6. Cortar fluxo UI “Iniciar = já estou dentro” só após shell + seletor (Fase 2).

## 10. Fora de escopo desta fatia

- Redesign do Chat (próxima conversa de produto).
- RAG de clima / Apify ( continua plano separado).
- pgbouncer / infra VPS.
- Alterar recorte SPEC-BRASIL ou funções `api.*`.

## 11. Artefatos

| Artefato | Caminho |
|---|---|
| Este contrato | `docs/CONTRATO-PLATAFORMA-GESTAO.md` |
| Migration | `sql/migrations/001_plataforma_gestao.sql` |
| Patch idempotente (runtime) | `sql/patch_gestao_v3.sql` (+ espelho `mcp/sql/`) |
| Aplicação no boot Gestão | `mcp/gestao/schema.py` |
| Store + API P1–P4 | `plataforma.py`, `routes_plataforma.py`, `auditoria.py`, `perfil_policy.py` |

## 12. Próximos passos de implementação

1. Deploy mcp-api com todo o pacote P0–P4.
2. Redesign do Chat (próxima conversa de produto).
