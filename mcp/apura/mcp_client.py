"""Cliente HTTP interno para o MCP."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from apura.tools import TOOL_TO_MCP


def _base_url() -> str:
    return os.environ.get("MCP_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")


async def chamar_mcp(tool_name: str, params: dict[str, Any], mcp_token: str) -> Any:
    method = TOOL_TO_MCP.get(tool_name)
    if not method:
        return {"erro": f"tool desconhecida: {tool_name}"}
    body = {"method": method, "params": params}
    if method == "catalogo":
        body["params"] = {}
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{_base_url()}/mcp",
            json=body,
            headers={"Authorization": f"Bearer {mcp_token}"},
        )
        if r.status_code >= 400:
            return {"erro": r.text, "status": r.status_code}
        return r.json()


def resumir_resultado(result: Any, max_chars: int = 12000) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "… [truncado]"
