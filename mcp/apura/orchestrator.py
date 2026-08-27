"""Orquestrador (tools + MCP) + redator expert (resposta final)."""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from apura.export import exportar_html
from apura.mcp_client import chamar_mcp, resumir_resultado
from apura.prompt import SYSTEM_ORCHESTRATOR, SYSTEM_WRITER
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


def _compactar_consultas(tool_log: list[dict[str, Any]]) -> str:
    if not tool_log:
        return "(Nenhuma consulta à base nesta rodada.)"
    partes: list[str] = []
    for tr in tool_log:
        partes.append(f"## {tr.get('tool', '?')} — params: {json.dumps(tr.get('params', {}), ensure_ascii=False)}")
        res = tr.get("result")
        if not isinstance(res, dict):
            partes.append(str(res)[:1500])
            continue
        status = res.get("status", "")
        if status == "fora_do_recorte":
            partes.append(f"status: fora_do_recorte | {res.get('mensagem', '')}")
            continue
        if status == "vazio":
            partes.append("status: vazio | zero eleitos neste recorte (filtro aplicado)")
            continue
        nota = res.get("nota_metodologica") or res.get("mensagem") or ""
        if nota:
            partes.append(f"nota: {nota}")
        linhas = res.get("linhas")
        if isinstance(linhas, list):
            partes.append(json.dumps(linhas, ensure_ascii=False, default=str)[:6000])
        else:
            partes.append(resumir_resultado(res, max_chars=6000))
    return "\n\n".join(partes)


def _notas_orquestrador(content: str | None) -> str:
    if not content:
        return ""
    text = content.strip()
    if text.startswith("PENDENTE:"):
        return text
    if text == "SEM_DADOS":
        return "SEM_DADOS"
    return ""


def _pediu_relatorio_html(mensagem: str) -> bool:
    return bool(_RELATORIO_RE.search(mensagem or ""))


def _system_redator(skills_text: str) -> str:
    if not skills_text.strip():
        return SYSTEM_WRITER
    return (
        f"{SYSTEM_WRITER}\n\n"
        "--- SKILLS DO USUÁRIO (tom, estrutura e estilo; não alteram fontes de dados) ---\n"
        f"{skills_text.strip()}"
    )


def _entrada_redator(
    pergunta: str,
    historico: list[dict[str, str]],
    tool_log: list[dict[str, Any]],
    notas: str,
) -> str:
    return (
        f"PERGUNTA_ATUAL:\n{pergunta}\n\n"
        f"HISTORICO_RECENTE:\n{_historico_redator(historico)}\n\n"
        f"PENDENTE_ORQUESTRADOR:\n{notas or '(nenhum)'}\n\n"
        f"DADOS_OFICIAIS:\n{_compactar_consultas(tool_log)}"
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
    for h in historico[-6:]:
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


async def executar_chat(
    historico: list[dict[str, str]],
    mcp_token: str,
    skills_text: str = "",
) -> AsyncIterator[str]:
    """Gera eventos SSE: status, token, done (opcional relatorio_html), error."""
    pergunta = _ultima_pergunta(historico)
    orch_messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_ORCHESTRATOR}]
    orch_messages.extend(_historico_orquestrador(historico))

    tool_log: list[dict[str, Any]] = []
    notas = ""

    try:
        for _ in range(_MAX_TOOL_ROUNDS):
            yield _sse("status", {"fase": "planejando"})
            r = await _openrouter(orch_messages, model=_orchestrator_model(), tools=MCP_TOOLS, stream=False)
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
                    yield _sse("status", {"fase": "consultando", "tool": name})
                    result = await chamar_mcp(name, args, mcp_token)
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

        yield _sse("status", {"fase": "redigindo"})
        writer_messages = [
            {"role": "system", "content": _system_redator(skills_text)},
            {"role": "user", "content": _entrada_redator(pergunta, historico, tool_log, notas)},
        ]
        full_parts: list[str] = []
        async for token in _stream_resposta(_writer_model(), writer_messages):
            full_parts.append(token)
            yield _sse("token", {"text": token})
        full = "".join(full_parts)

        dados = {"tool_results": tool_log} if tool_log else None
        done: dict[str, Any] = {"conteudo": full, "dados": dados}
        if _pediu_relatorio_html(pergunta) and tool_log:
            titulo = pergunta[:80] or "Relatório Apura"
            done["relatorio_html"] = exportar_html(dados, full, titulo)
        yield _sse("done", done)

    except RuntimeError as exc:
        yield _sse("error", {"mensagem": str(exc)})
    except Exception as exc:
        yield _sse("error", {"mensagem": f"Falha no orquestrador: {exc}"})
