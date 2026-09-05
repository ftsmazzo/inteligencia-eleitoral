# Apura · arquitetura multiagente (Trilho A)

Status: Fase 0–4 implementadas no código (`mcp/apura/`). Deploy se860g sob demanda.

## Camadas

| Camada | Onde |
|--------|------|
| Política de dados | `prompts/politica_dados.py` |
| Protocolo Ary / perfis | `prompts/protocolo_airy.py` + `missao_state.py` |
| Voz redator | `prompts/voz.py` |
| Orquestrador system | `prompts/orquestrador.py` |
| Hub SSE | `agents/hub.py` (fachada `orchestrator.executar_chat`) |
| Camadas Fato/Indício | `agents/camadas.py` + `agents/registry.py` |
| Capacidades OR | `capabilities.py` (web/PDF/visão/áudio/imagem/HTML/ops) |

## Perfis (vínculo no login)

- `consultor_minimo` → **Operacional**
- `analista` → **Analista**
- `estrategista` / `coordenador` → **Estrategista** (+ protocolo Ary)

## Schema

`sql/patch_gestao_v5.sql` — contatos, tarefas, tools novas; aplicado em `gestao.schema.ensure_schema`.
