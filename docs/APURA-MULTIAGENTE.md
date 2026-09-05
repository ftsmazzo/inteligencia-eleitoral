# Apura · arquitetura multiagente (Trilho A)

Status: Fase 0–4 no código. **Ativar Ary** = modo pleno (modelo robusto + agentes), sem briefing.

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
- `estrategista` / `coordenador` → **Estrategista** (+ pode Ativar Ary)

## Ativar Ary / Airy

No Chat: `Ativar Ary` (também aceita Airy).

- Sobe modelos: `APURA_ARY_ORCHESTRATOR_MODEL` / `APURA_ARY_WRITER_MODEL` (default `openai/gpt-4o`)
- Libera uso pleno dos agentes/tools do perfil
- **Não** inicia briefing nem questionário
- Desligar: `Desativar Ary`

## Schema

`sql/patch_gestao_v5.sql` — contatos, tarefas, tools novas; aplicado em `gestao.schema.ensure_schema`.
