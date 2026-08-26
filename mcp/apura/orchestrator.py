"""Orquestrador OpenRouter + MCP com streaming SSE."""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from apura.mcp_client import chamar_mcp, resumir_resultado
from apura.prompt import SYSTEM
from apura.tools import MCP_TOOLS

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_MAX_TOOL_ROUNDS = 6


def _model() -> str:
    return os.environ.get("APURA_MODEL", "openai/gpt-4o-mini")


def _headers() -> dict[str, str]:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY não configurado")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"),
        "X-Title": "Apura · Inteligência Eleitoral Brasil",
    }


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _openrouter(messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> Any:
    body: dict[str, Any] = {"model": _model(), "messages": messages, "temperature": 0.4}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if stream:
        body["stream"] = True
    async with httpx.AsyncClient(timeout=120.0) as client:
        return await client.post(_OPENROUTER, headers=_headers(), json=body)


async def executar_chat(
    historico: list[dict[str, str]],
    mcp_token: str,
) -> AsyncIterator[str]:
    """Gera eventos SSE: status, token, done, error."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    for h in historico:
        messages.append({"role": h["papel"], "content": h["conteudo"]})

    tool_log: list[dict[str, Any]] = []

    try:
        for _ in range(_MAX_TOOL_ROUNDS):
            yield _sse("status", {"fase": "pensando"})
            r = await _openrouter(messages, MCP_TOOLS, stream=False)
            if r.status_code >= 400:
                yield _sse("error", {"mensagem": r.text[:500]})
                return
            data = r.json()
            choice = data["choices"][0]["message"]
            tool_calls = choice.get("tool_calls") or []

            if tool_calls:
                messages.append(choice)
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": resumir_resultado(result),
                        }
                    )
                continue

            # Resposta final
            yield _sse("status", {"fase": "redigindo"})
            full = choice.get("content") or ""
            if full:
                chunk_size = 36
                for i in range(0, len(full), chunk_size):
                    yield _sse("token", {"text": full[i : i + chunk_size]})
            else:
                sr = await _openrouter(messages, None, stream=True)
                if sr.status_code >= 400:
                    yield _sse("error", {"mensagem": sr.text[:500]})
                    return
                full_parts: list[str] = []
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
                        full_parts.append(text)
                        yield _sse("token", {"text": text})
                full = "".join(full_parts)

            yield _sse(
                "done",
                {
                    "conteudo": full,
                    "dados": {"tool_results": tool_log} if tool_log else None,
                },
            )
            return

        yield _sse("error", {"mensagem": "Limite de consultas atingido nesta mensagem."})
    except RuntimeError as exc:
        yield _sse("error", {"mensagem": str(exc)})
    except Exception as exc:
        yield _sse("error", {"mensagem": f"Falha no orquestrador: {exc}"})
