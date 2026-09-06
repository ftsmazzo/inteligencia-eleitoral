"""Orquestrador Apura — delega ao hub multiagente (SSE estável)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from apura.agents.hub import executar_hub
from apura.missao_state import MissaoState


async def executar_chat(
    historico: list[dict[str, str]],
    mcp_token: str,
    skills_text: str = "",
    modo_narrativa: bool = False,
    campanha_ctx: str = "",
    politica: dict[str, Any] | None = None,
    missao_state: MissaoState | None = None,
    anexos: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Gera eventos SSE: status, token, done (opcional relatorio_html/mapa/imagem), error."""
    async for chunk in executar_hub(
        historico,
        mcp_token,
        skills_text=skills_text,
        modo_narrativa=modo_narrativa,
        campanha_ctx=campanha_ctx,
        politica=politica,
        missao_state=missao_state,
        anexos=anexos,
    ):
        yield chunk
