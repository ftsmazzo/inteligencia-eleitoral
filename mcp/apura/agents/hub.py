"""Hub multiagente — fachada SSE compatível com executar_chat legado."""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from apura.agents.camadas import compactar_por_camadas
from apura.agents.registry import plano_de_tool_log
from apura.export import exportar_html
from apura.mcp_client import chamar_mcp, resumir_resultado
from apura.missao_state import (
    MissaoState,
    aplicar_comando,
    detectar_comando,
    resumo_para_prompt,
)
from apura.prompt import (
    NARRATIVA_ORCHESTRATOR,
    PROTOCOLO_AIRY_CRIACAO,
    PROTOCOLO_AIRY_ELEITORAL,
    PROTOCOLO_ANALISTA,
    PROTOCOLO_OPERACIONAL,
    SYSTEM_ORCHESTRATOR,
    VOZ_OPERACIONAL,
    VOZ_REDATOR,
)
from apura.tools import MCP_TOOLS

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_MAX_TOOL_ROUNDS = 12
_RELATORIO_RE = re.compile(
    r"relat[oó]rio|em\s+html|formato\s+html|exporte?\s+(?:em\s+)?html|monte?\s+(?:um\s+)?html",
    re.I,
)


def _orchestrator_model() -> str:
    return (
        os.environ.get("APURA_ORCHESTRATOR_MODEL")
        or os.environ.get("APURA_MODEL")
        or "openai/gpt-4o-mini"
    )


def _writer_model() -> str:
    return os.environ.get("APURA_WRITER_MODEL") or "openai/gpt-4o"


def _openrouter_key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY não configurado no servidor")
    if not key.startswith("sk-or-"):
        raise RuntimeError(
            "OPENROUTER_API_KEY inválida no servidor — gere uma chave em openrouter.ai/keys "
            "(formato sk-or-v1-...) e atualize a variável no EasyPanel (serviço mcp-api)."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_openrouter_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"),
        "X-Title": "Apura - Inteligencia Eleitoral Brasil",
    }


def _erro_openrouter(status: int, body: str) -> str:
    try:
        data = json.loads(body)
        err = data.get("error") or {}
        if isinstance(err, str):
            msg = err
            meta: dict[str, Any] = {}
        else:
            msg = err.get("message") or data.get("message") or body
            meta = err.get("metadata") or {}
        raw = meta.get("raw") if isinstance(meta, dict) else None
        if isinstance(raw, str) and raw.strip() and raw.strip() not in msg:
            msg = f"{msg} — {raw.strip()[:320]}"
    except json.JSONDecodeError:
        msg = body
    if status == 401:
        return (
            "OpenRouter recusou a autenticação. Verifique OPENROUTER_API_KEY no EasyPanel "
            f"(serviço mcp-api): chave válida em openrouter.ai/keys. Detalhe: {msg}"
        )
    if status == 402:
        return "Créditos insuficientes na conta OpenRouter — adicione saldo em openrouter.ai/credits."
    if status == 400:
        return (
            f"OpenRouter recusou a requisição (400): {msg[:360]}. "
            "Se persistir, reduza o escopo da pergunta ou ajuste APURA_ORCHESTRATOR_MODEL / APURA_WRITER_MODEL."
        )
    return f"OpenRouter retornou erro {status}: {msg[:360]}"


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _ultima_pergunta(historico: list[dict[str, str]]) -> str:
    for h in reversed(historico):
        if h.get("papel") == "user":
            return h.get("conteudo", "").strip()
    return ""


def _historico_redator(historico: list[dict[str, str]]) -> str:
    linhas: list[str] = []
    for h in historico[-8:]:
        papel = "Usuário" if h.get("papel") == "user" else "Apura"
        linhas.append(f"{papel}: {(h.get('conteudo') or '')[:900]}")
    return "\n".join(linhas)


def _notas_orquestrador(content: str | None) -> str:
    if not content:
        return ""
    text = content.strip()
    if text.startswith("PENDENTE:"):
        return text
    if text == "SEM_DADOS":
        return "SEM_DADOS"
    if text == "ESCOPO_DIRETO" or text.startswith("ESCOPO_DIRETO"):
        return "ESCOPO_DIRETO"
    if text.startswith("PROTOCOLO:"):
        return text
    return ""


def _pediu_relatorio_html(mensagem: str) -> bool:
    return bool(_RELATORIO_RE.search(mensagem or ""))


def _system_protocolo(state: MissaoState) -> str:
    if state.caminho_curto:
        return PROTOCOLO_OPERACIONAL
    if state.perfil == "analista":
        return PROTOCOLO_ANALISTA
    parts = [PROTOCOLO_AIRY_ELEITORAL]
    if state.pack_criacao:
        parts.append(PROTOCOLO_AIRY_CRIACAO)
    parts.append(resumo_para_prompt(state))
    return "\n\n".join(parts)


def _system_redator(skills_text: str, campanha_ctx: str, state: MissaoState) -> str:
    base = VOZ_OPERACIONAL if state.caminho_curto else VOZ_REDATOR
    proto = _system_protocolo(state)
    base = f"{base}\n\n--- PROTOCOLO / PERFIL ---\n{proto}"
    if skills_text.strip():
        base = (
            f"{base}\n\n"
            "--- SKILLS DO USUÁRIO (tom/estilo; não alteram fontes) ---\n"
            f"{skills_text.strip()}"
        )
    if campanha_ctx.strip():
        base = f"{base}\n\n{campanha_ctx.strip()}"
    return base


def _entrada_redator(
    pergunta: str,
    historico: list[dict[str, str]],
    tool_log: list[dict[str, Any]],
    notas: str,
    state: MissaoState,
) -> str:
    return (
        f"PERGUNTA_ATUAL:\n{pergunta}\n\n"
        f"ESTADO_MISSAO:\n{resumo_para_prompt(state)}\n\n"
        f"HISTORICO_RECENTE:\n{_historico_redator(historico)}\n\n"
        f"PENDENTE_ORQUESTRADOR:\n{notas or '(nenhum)'}\n\n"
        f"DADOS_OFICIAIS:\n{compactar_por_camadas(tool_log)}"
    )


def _msg_assistant(choice: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": choice.get("content")}
    tool_calls = choice.get("tool_calls")
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc["id"],
                "type": tc.get("type") or "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments") or "{}",
                },
            }
            for tc in tool_calls
        ]
    return out


def _historico_orquestrador(historico: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    for h in historico[-10:]:
        papel = h.get("papel")
        if papel not in ("user", "assistant"):
            continue
        msgs.append({"role": papel, "content": (h.get("conteudo") or "")[:2500]})
    return msgs


async def _openrouter(
    messages: list[dict],
    *,
    model: str,
    tools: list[dict] | None = None,
    stream: bool = False,
    temperature: float = 0.3,
) -> Any:
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if stream:
        body["stream"] = True
    async with httpx.AsyncClient(timeout=120.0) as client:
        return await client.post(_OPENROUTER, headers=_headers(), json=body)


async def _stream_resposta(model: str, messages: list[dict], temperature: float = 0.55) -> AsyncIterator[str]:
    sr = await _openrouter(messages, model=model, stream=True, temperature=temperature)
    if sr.status_code >= 400:
        nr = await _openrouter(messages, model=model, stream=False, temperature=temperature)
        if nr.status_code >= 400:
            raise RuntimeError(_erro_openrouter(nr.status_code, nr.text))
        content = nr.json()["choices"][0]["message"].get("content") or ""
        if content:
            yield content
        return
    async for line in sr.aiter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk["choices"][0].get("delta", {})
        text = delta.get("content") or ""
        if text:
            yield text


def _enriquecer_clima_params(args: dict[str, Any], campanha_ctx: str) -> dict[str, Any]:
    """Clima quente: se q vazio e há escopo, injeta nome do candidato."""
    out = dict(args or {})
    if (out.get("q") or "").strip():
        return out
    m = re.search(
        r"candidato[^\n:]{0,40}:\s*([^\n]+)",
        campanha_ctx or "",
        re.I,
    )
    if m:
        out["q"] = m.group(1).strip()[:120]
        out.setdefault("janela_horas", 168)
    return out


async def executar_hub(
    historico: list[dict[str, str]],
    mcp_token: str,
    skills_text: str = "",
    modo_narrativa: bool = False,
    campanha_ctx: str = "",
    politica: dict[str, Any] | None = None,
    missao_state: MissaoState | None = None,
) -> AsyncIterator[str]:
    """Gera eventos SSE: status, token, done, error. Inclui missao_state no done.dados."""
    from apura.perfil_policy import filtrar_mcp_tools, resumo_politica, tool_permitida

    pergunta = _ultima_pergunta(historico)
    pol = politica or {
        "bypass": True,
        "tools": set(),
        "modelo_orquestrador": _orchestrator_model(),
        "modelo_redator": _writer_model(),
        "fonte": "sem_politica",
    }
    state = missao_state or MissaoState(perfil=(pol.get("perfil_slug") or "analista"))
    if pol.get("bypass"):
        # Super gestor: acesso pleno + protocolo Ary disponível
        state.perfil = "estrategista"
    elif pol.get("perfil_slug"):
        from apura.missao_state import perfil_de_slug

        state.perfil = perfil_de_slug(pol.get("perfil_slug")).value

    cmd = detectar_comando(pergunta)
    state = aplicar_comando(state, cmd, pergunta)

    orch_model = (pol.get("modelo_orquestrador") or _orchestrator_model()).strip()
    writer_model = (pol.get("modelo_redator") or _writer_model()).strip()
    tools = filtrar_mcp_tools(pol) if not pol.get("bypass") else MCP_TOOLS
    if not tools:
        yield _sse(
            "error",
            {"mensagem": "Seu Perfil não tem tools liberadas. Peça ajuste ao gestor da campanha."},
        )
        return

    # Protocolo Ary em briefing/matriz: redator conduz; tools só se pedido explícito de dado
    _etapas_protocolo = {
        "briefing_objetivo",
        "briefing_estilo",
        "briefing_papel",
        "briefing_detalhe",
        "briefing_refs",
        "matriz",
    }
    _pedido_dado = any(
        k in pergunta.lower()
        for k in (
            "vot",
            "eleito",
            "urna",
            "tse",
            "cifra",
            "instagram",
            "@",
            "clima",
            "gasto",
            "pesquis",
            "pdf",
            "mapa",
        )
    )
    so_protocolo = (
        state.usa_protocolo_airy
        and state.etapa in _etapas_protocolo
        and (cmd is not None or not _pedido_dado)
    )

    orch_system = SYSTEM_ORCHESTRATOR
    if modo_narrativa or state.perfil == "estrategista":
        orch_system = f"{SYSTEM_ORCHESTRATOR}\n\n{NARRATIVA_ORCHESTRATOR}"
    orch_system = f"{orch_system}\n\n{_system_protocolo(state)}"
    if campanha_ctx.strip():
        orch_system = (
            f"{orch_system}\n\n"
            "Contexto desta campanha (escopo + memória). Números oficiais só via tools.\n"
            f"{campanha_ctx.strip()[:6000]}"
        )
    slug = pol.get("perfil_slug")
    if slug and not pol.get("bypass"):
        orch_system = (
            f"{orch_system}\n\n"
            f"Perfil de acesso: {slug}. Use apenas tools disponíveis."
        )

    tool_log: list[dict[str, Any]] = []
    notas = ""

    try:
        if so_protocolo:
            notas = (
                f"PROTOCOLO:\netapa={state.etapa}\ncomando={cmd or 'conteudo'}\n"
                f"aguardando_ok={state.aguardando_ok}\n"
                "Conduza a próxima fala do protocolo Ary (pergunta ou resumo+OK)."
            )
            yield _sse("status", {"fase": "protocolo", "etapa": state.etapa, "perfil": state.perfil})
        else:
            orch_messages: list[dict[str, Any]] = [{"role": "system", "content": orch_system}]
            orch_messages.extend(_historico_orquestrador(historico))
            campanha_id = pol.get("campanha_id")
            usuario_id = pol.get("usuario_id")

            for _ in range(_MAX_TOOL_ROUNDS):
                yield _sse(
                    "status",
                    {"fase": "planejando", "modelo": orch_model, "perfil": state.perfil},
                )
                r = await _openrouter(orch_messages, model=orch_model, tools=tools, stream=False)
                if r.status_code >= 400:
                    yield _sse("error", {"mensagem": _erro_openrouter(r.status_code, r.text)})
                    return
                choice = r.json()["choices"][0]["message"]
                tool_calls = choice.get("tool_calls") or []

                if tool_calls:
                    orch_messages.append(_msg_assistant(choice))
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        if name == "consultar_clima":
                            args = _enriquecer_clima_params(args, campanha_ctx)
                        if not tool_permitida(pol, name):
                            result = {
                                "erro": "tool_negada_pelo_perfil",
                                "tool": name,
                                "perfil": pol.get("perfil_slug"),
                                "mensagem": (
                                    f"Tool '{name}' não permitida no Perfil "
                                    f"{pol.get('perfil_slug') or 'atual'}."
                                ),
                            }
                            tool_log.append({"tool": name, "params": args, "result": result})
                            orch_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": resumir_resultado(result, max_chars=2000),
                                }
                            )
                            continue
                        yield _sse("status", {"fase": "consultando", "tool": name})
                        result = await chamar_mcp(
                            name,
                            args,
                            mcp_token,
                            campanha_id=campanha_id,
                            usuario_id=usuario_id,
                        )
                        tool_log.append({"tool": name, "params": args, "result": result})
                        orch_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": resumir_resultado(result, max_chars=6000),
                            }
                        )
                    continue

                notas = _notas_orquestrador(choice.get("content"))
                break
            else:
                yield _sse("error", {"mensagem": "Limite de consultas atingido nesta mensagem."})
                return

        state.agentes_plano = plano_de_tool_log(tool_log)
        yield _sse("status", {"fase": "redigindo", "modelo": writer_model})
        writer_messages = [
            {"role": "system", "content": _system_redator(skills_text, campanha_ctx, state)},
            {
                "role": "user",
                "content": _entrada_redator(pergunta, historico, tool_log, notas, state),
            },
        ]
        full_parts: list[str] = []
        async for token in _stream_resposta(writer_model, writer_messages):
            full_parts.append(token)
            yield _sse("token", {"text": token})
        full = "".join(full_parts)

        # Se redator produziu matriz em markdown list, tenta capturar
        if state.etapa == "matriz" and full:
            bullets = re.findall(r"^\s*[-*]\s+(.+)$", full, re.M)
            if len(bullets) >= 2:
                state.matriz = [b.strip()[:200] for b in bullets[:30]]

        dados: dict[str, Any] = {
            "politica": resumo_politica(pol),
            "missao_state": state.to_dict(),
            "agentes": state.agentes_plano,
        }
        if tool_log:
            dados["tool_results"] = tool_log
        done: dict[str, Any] = {"conteudo": full, "dados": dados}
        if _pediu_relatorio_html(pergunta) and tool_log:
            titulo = pergunta[:80] or "Relatório Apura"
            done["relatorio_html"] = exportar_html(dados, full, titulo)
        # Mapa HTML gerado pela tool
        for tr in tool_log:
            if tr.get("tool") == "gerar_mapa_html" and isinstance(tr.get("result"), dict):
                html = tr["result"].get("html")
                if html:
                    done["mapa_html"] = html
        yield _sse("done", done)

    except RuntimeError as exc:
        yield _sse("error", {"mensagem": str(exc)})
    except Exception as exc:
        yield _sse("error", {"mensagem": f"Falha no hub Apura: {exc}"})
