# Sprints — Gestão Apura

Produto: camada **Gestão** → Chat + Radar com Perfil/dossiê/Base.

Contrato da virada multi-campanha: `docs/CONTRATO-PLATAFORMA-GESTAO.md`.

## Status

| Sprint | Entrega | Status |
|--------|---------|--------|
| **1** | Schema escopo + wizard + aba Gestão | feito |
| **2** | Motor Base de Verdade + Perfil de Eleitor | feito |
| **3** | Upload HTML → blocos memória | feito |
| **4** | Seed Radar + coordenador + liberar equipe | feito |
| **5** | Apura injeta Perfil + blocos no prompt | feito |
| **Deploy P0–P4** | `1cb4c29` em `ftsmazzo/inteligencia-eleitoral` (push ok) · redeploy se860g **pendente** (MCP `inteligendia-eleitoral` travado) | pendente validação |
| **P0** | Contrato + `patch_gestao_v3` (Perfis, membros N:N, módulos, eventos) | feito (código; aplicar na VPS no próximo boot/deploy) |
| **P1** | APIs plataforma (frota, criar, entrar, membros, tokens) | feito (código; deploy aplica v3 + rotas) |
| **P2** | UI shell Gestão + seletor pós-login | feito (código em `mcp/static/apura/index.html`) |
| **P3** | Orchestrator/MCP leem Perfil do vínculo/token | feito (`apura/perfil_policy.py`) |
| **P4** | Painel interações/logs + IA governança | feito (`gestao/auditoria.py` + aba Auditoria) |
| **P5** | Shell multi-tenant (1B+2C): sidebar sem tools; Operar/Administrar; dash+quotas+conversas | feito (código; deploy se860g) |
| **Multiagente** | Hub + MissaoState + Ary + capacidades OR + ops (patch_gestao_v5) | feito (código; smoke estático ok; deploy pendente) |

## UI Plataforma (P2 → P5)

- **Shell plataforma** (`shellMode=plataforma`): super sem Chat/Radar/Skills/sessões; abas Visão geral · Frota · Quotas · Conversas · Eventos.
- **Operar** → workspace da campanha; **Administrar** → filtro no shell; **Voltar à plataforma** → `/sair`.
- **Seletor** (`#seletor-screen`): pós-login se N vínculos e sem campanha ativa (não-super).
- **Campanha** (`#gestao-campanha-panel`): wizard de escopo + abas Equipe/Perfis e Tokens MCP (só no workspace).
- Chip da campanha ativa só no workspace.

## API Plataforma (`/apura/api/gestao/plataforma`)

| Method | Path | Quem |
|--------|------|------|
| GET | `/eu` | autenticado — contexto + vínculos + super |
| GET/POST | `/campanhas` | listar (super=todas; senão vínculos) / criar (só super) |
| GET | `/campanhas/{id}` | super ou membro |
| POST | `/entrar` · `/sair` | define/limpa `campanha_ativa_id` |
| GET/POST/DELETE | `/campanhas/{id}/membros` | super ou coordenador |
| GET/PATCH | `/perfis` · `/perfis/{slug\|id}` | GET todos; PATCH só super |
| GET/POST | `/campanhas/{id}/tokens` | emitir token MCP (perfil) — token completo só no POST |
| GET | `/eventos` | só super |
| GET | `/quotas` | só super |
| PATCH | `/usuarios/{id}/quota` · `/campanhas/{id}/quota` | só super |
| GET | `/auditoria/resumo` · `/interacoes` · `/sessoes` · `/sessoes/{id}/mensagens` | só super |
| POST | `/auditoria/sugerir` | só super |

`GET /apura/api/auth/eu` também devolve `is_super_gestor`, `vinculos`, `precisa_seletor`.

## Enforcement Perfil (P3)

- `mcp/apura/perfil_policy.py` — resolve modelos + tools (membro da campanha ativa, token MCP, super=bypass, fallback `analista`).
- Chat Apura: orquestrador só vê tools do Perfil; tool fora da lista → `tool_negada_pelo_perfil`; `dados_json.politica` no `done`.
- `/mcp` e REST `/v1/*`: `_token_ok(..., method)` → 403 se método fora do Perfil do token.
- Token mestre (`MCP_TOKEN`) continua bypass.

## Auditoria (P4) — só super gestores

| Method | Path | Função |
|--------|------|--------|
| GET | `/auditoria/resumo?dias=` | KPIs, por usuário, tools, campanhas |
| GET | `/auditoria/interacoes` | Timeline de mensagens (+ tools/perfil) |
| GET | `/eventos` | Log `ctl.evento_acesso` |
| POST | `/auditoria/sugerir` | Heurísticas + IA (sem cifras eleitorais) |

UI: aba **Auditoria** na frota. Eventos gravados em login e `chat_pergunta`.

## Fluxo operacional

1. Gestão → Iniciar → ano/cargo/UF/candidato → Salvar escopo  
2. **Gerar Base + Perfil** (motor)  
3. (Opcional) upload dossiê HTML  
4. Seed Radar / Liberar equipe  
5. Equipe usa Chat + Radar; Apura lê `ctl.campanha_memoria`

## API Gestão

| Path | Função |
|------|--------|
| GET/POST status, iniciar, candidatos, escopo, ambiente | S1 |
| POST `/motor` | S2 Base + Perfil (+ seed radar) |
| GET `/memoria` | lista blocos |
| POST `/dossie` | HTML no JSON `{html, nome_arquivo}` |
| POST `/seed-radar` | alvos a partir do escopo |
| POST `/liberar` | pronto + equipe_liberada |

Cifras = Trilha A. Memória = contexto/`indicio` (exceto blocos `nivel=fato` do motor).
