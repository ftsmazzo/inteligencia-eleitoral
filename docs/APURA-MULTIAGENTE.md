# Apura · arquitetura multiagente (Trilho A)

Status: Fase 0–4 no código. **Ativar Ary** = modo pleno (modelos top + agentes), sem briefing.

Catálogo canônico: `mcp/apura/modelos.py` (IDs OpenRouter verificados).

## Princípio de modelos

Cada papel usa a IA que combina com a tarefa — **não** GPT-4o/4o-mini genéricos.

| Função | Modelo | Por quê |
|--------|--------|---------|
| Orquestração / tools | `google/gemini-2.5-flash` | Tool-calling forte, barato |
| Orquestração Ary | `google/gemini-2.5-pro` | Mais cabeça no plano sem gastar Sonnet no roteamento |
| Texto final / reflexão | `anthropic/claude-sonnet-4.6` | Prosa e julgamento |
| Texto Ary | `anthropic/claude-sonnet-5` | Reflexão complexa / redator máximo |
| Consultor (orch) | `google/gemini-2.5-flash-lite` | Triagem leve |
| Consultor (texto) | `anthropic/claude-haiku-4.5` | Resposta curta, Anthropic barato |
| Web | `perplexity/sonar` (+ `sonar-pro` no Ary) | Busca nativa |
| PDF / OCR | `mistralai/ministral-14b-2512` + engine `mistral-ocr` | OCR Mistral + LLM visão barato |
| Áudio | `google/gemini-2.5-flash` (`input_audio`) | Transcrição por anexo/URL |
| Imagem | `google/gemini-2.5-flash-image` via `POST /api/v1/images` | Artefato visual real |
| Plano HTML | template `plano_html.py` | Artefato estável (não LLM livre) |
| PDF / visão genérica | `google/gemini-2.5-flash` (só visão) | Multimodal econômico |
| Radar / governança | Flash / Flash-lite | Volume, baixo risco |

Overrides (EasyPanel): `APURA_ORCHESTRATOR_MODEL`, `APURA_WRITER_MODEL`, `APURA_ARY_*`, `APURA_WEB_MODEL`, etc. **Remova** defaults antigos `openai/gpt-4o*` se ainda estiverem setados — env força e anula o catálogo.

## Camadas

| Camada | Onde |
|--------|------|
| Catálogo de modelos | `modelos.py` |
| Política de dados | `prompts/politica_dados.py` |
| Protocolo Ary / perfis | `prompts/protocolo_airy.py` + `missao_state.py` |
| Voz redator | `prompts/voz.py` |
| Orquestrador system | `prompts/orquestrador.py` |
| Hub SSE | `agents/hub.py` (fachada `orchestrator.executar_chat`) |
| Camadas Fato/Indício | `agents/camadas.py` + `agents/registry.py` |
| Capacidades OR | `capabilities.py` (web/PDF/visão/áudio/imagem/HTML/ops) |

## Perfis (vínculo no login)

| Slug | Orquestrador | Redator |
|------|--------------|---------|
| `consultor_minimo` | Flash Lite | Haiku 4.5 |
| `analista` | Flash | Sonnet 4.6 |
| `estrategista` / `coordenador` | Gemini 2.5 Pro | Sonnet 4.6 |

Seeds: `sql/patch_gestao_v3.sql` + `patch_gestao_v6.sql` (UPDATE forçado).

## Ativar Ary / Airy

No Chat: `Ativar Ary` (também aceita Airy).

- Orquestrador → `google/gemini-2.5-pro` (`APURA_ARY_ORCHESTRATOR_MODEL`)
- Redator → `anthropic/claude-sonnet-5` (`APURA_ARY_WRITER_MODEL`)
- Libera uso pleno dos agentes/tools do perfil
- **Não** inicia briefing nem questionário
- Desligar: `Desativar Ary`

## Identidade & rival canônico

Contexto do chat (nessa ordem): **ESCOPO** → **ALVOS CANÔNICOS** → **CONHECIMENTO** (estratégias → dossiê → bases).

- “Nosso rival” = nomes do card ALVOS (Radar adversário, redes, rótulos no dossiê/estratégias).
- Proibido definir rival só pela nominata/vice de urna antiga.
- Bloco opcional `tipo=estrategias` em `ctl.campanha_memoria` (prioridade máxima na memória).
- Skill runtime: `SKILL_CAMPANHA_IDENTIDADE` (com escopo).
- Playbook duro (hub): pedido de estratégia/ângulo/contraste → força `consultar_memoria` (estratégias + pesquisas) + `consultar_clima` no rival; clima vazio → `pesquisar_web`.
- Gestão: formulário **Estratégias** (`POST /gestao/estrategias`) com rival + texto; tool chat `consultar_memoria`.

## Schema

`patch_gestao_v5` … `v7` (consultar_memoria nos perfis); aplicados em `gestao.schema.ensure_schema`.
