"""Política de Perfil em runtime: modelos OpenRouter + allowlist de tools.

Contrato: docs/CONTRATO-PLATAFORMA-GESTAO.md (P3).
Token mestre (MCP_TOKEN env) = bypass total.
"""
from __future__ import annotations

import os
from typing import Any

import psycopg

from apura.tools import MCP_TOOLS, TOOL_TO_MCP

MCP_TO_TOOL: dict[str, str] = {v: k for k, v in TOOL_TO_MCP.items()}


def _env_orch() -> str:
    return (
        os.environ.get("APURA_ORCHESTRATOR_MODEL")
        or os.environ.get("APURA_MODEL")
        or "openai/gpt-4o-mini"
    )


def _env_writer() -> str:
    return os.environ.get("APURA_WRITER_MODEL") or "openai/gpt-4o"


def _todas_tools() -> set[str]:
    return set(TOOL_TO_MCP.keys())


def _perfil_por_slug(conn: psycopg.Connection, slug: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT p.id::text, p.slug, p.nome, p.modelo_orquestrador, p.modelo_redator,
               p.quota_perguntas_max
        FROM ctl.perfil p
        WHERE p.slug = %s AND p.ativo IS TRUE
        """,
        (slug,),
    ).fetchone()
    if not row:
        return None
    tools = conn.execute(
        "SELECT tool_name FROM ctl.perfil_tool WHERE perfil_id = %s::uuid",
        (row[0],),
    ).fetchall()
    return {
        "perfil_id": row[0],
        "perfil_slug": row[1],
        "perfil_nome": row[2],
        "modelo_orquestrador": row[3] or _env_orch(),
        "modelo_redator": row[4] or _env_writer(),
        "quota_perguntas_max": row[5],
        "tools": {t[0] for t in tools} or _todas_tools(),
        "fonte": f"perfil:{row[1]}",
        "bypass": False,
    }


def _politica_plena(*, fonte: str) -> dict[str, Any]:
    return {
        "perfil_id": None,
        "perfil_slug": None,
        "perfil_nome": None,
        "modelo_orquestrador": _env_orch(),
        "modelo_redator": _env_writer(),
        "quota_perguntas_max": None,
        "tools": _todas_tools(),
        "fonte": fonte,
        "bypass": True,
    }


def politica_do_perfil_id(conn: psycopg.Connection, perfil_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT p.id::text, p.slug, p.nome, p.modelo_orquestrador, p.modelo_redator,
               p.quota_perguntas_max
        FROM ctl.perfil p
        WHERE p.id = %s::uuid AND p.ativo IS TRUE
        """,
        (perfil_id,),
    ).fetchone()
    if not row:
        return None
    tools = conn.execute(
        "SELECT tool_name FROM ctl.perfil_tool WHERE perfil_id = %s::uuid",
        (row[0],),
    ).fetchall()
    return {
        "perfil_id": row[0],
        "perfil_slug": row[1],
        "perfil_nome": row[2],
        "modelo_orquestrador": row[3] or _env_orch(),
        "modelo_redator": row[4] or _env_writer(),
        "quota_perguntas_max": row[5],
        "tools": {t[0] for t in tools} or _todas_tools(),
        "fonte": f"perfil:{row[1]}",
        "bypass": False,
    }


def politica_usuario(conn: psycopg.Connection, usuario_id: str, email: str) -> dict[str, Any]:
    """Resolve Perfil do vínculo na campanha ativa (ou legado). Super = bypass."""
    try:
        from gestao.plataforma import campanha_ativa_do_usuario, eh_super_gestor, membro_ativo

        if eh_super_gestor(conn, email):
            return _politica_plena(fonte="super_gestor")

        ativa = campanha_ativa_do_usuario(conn, usuario_id)
        if ativa:
            m = membro_ativo(conn, usuario_id, ativa[0])
            if m and m.get("perfil_id"):
                pol = politica_do_perfil_id(conn, m["perfil_id"])
                if pol:
                    pol["fonte"] = f"membro:{m.get('perfil_slug')}"
                    pol["campanha_id"] = ativa[0]
                    pol["papel_campanha"] = m.get("papel_campanha")
                    return pol
    except Exception:
        pass

    # Fallback seguro: Analista (não abre tudo por omissão)
    pol = _perfil_por_slug(conn, "analista")
    if pol:
        pol["fonte"] = "fallback:analista"
        return pol
    return _politica_plena(fonte="fallback:env")


def politica_token(conn: psycopg.Connection, token: str, *, master: str = "") -> dict[str, Any]:
    if master and token == master:
        return _politica_plena(fonte="token_mestre")
    row = conn.execute(
        """
        SELECT perfil_id::text, campanha_id::text, apura_usuario_id::text
        FROM ctl.mcp_token
        WHERE token = %s AND ativo IS TRUE
        """,
        (token,),
    ).fetchone()
    if not row:
        return _politica_plena(fonte="token_desconhecido")  # _token_ok já barraria

    perfil_id, campanha_id, usuario_id = row[0], row[1], row[2]

    if perfil_id:
        pol = politica_do_perfil_id(conn, perfil_id)
        if pol:
            pol["campanha_id"] = campanha_id
            pol["fonte"] = f"token:{pol['perfil_slug']}"
            return pol

    # Token de pessoa Apura: tenta vínculo
    if usuario_id:
        email_row = conn.execute(
            "SELECT email FROM ctl.apura_usuario WHERE id = %s::uuid",
            (usuario_id,),
        ).fetchone()
        if email_row:
            pol = politica_usuario(conn, usuario_id, email_row[0])
            pol["fonte"] = f"token_usuario:{pol.get('fonte')}"
            return pol

    pol = _perfil_por_slug(conn, "analista")
    if pol:
        pol["campanha_id"] = campanha_id
        pol["fonte"] = "token_fallback:analista"
        return pol
    return _politica_plena(fonte="token_fallback:env")


def filtrar_mcp_tools(politica: dict[str, Any]) -> list[dict]:
    if politica.get("bypass"):
        return MCP_TOOLS
    allowed = politica.get("tools") or set()
    out: list[dict] = []
    for t in MCP_TOOLS:
        name = (t.get("function") or {}).get("name")
        if name in allowed:
            out.append(t)
    return out


def tool_permitida(politica: dict[str, Any], tool_name: str) -> bool:
    if politica.get("bypass"):
        return True
    return tool_name in (politica.get("tools") or set())


def metodo_permitido(politica: dict[str, Any], method: str) -> bool:
    if politica.get("bypass"):
        return True
    tool = MCP_TO_TOOL.get(method)
    if not tool:
        # método desconhecido: deixa o handler 400
        return True
    return tool_permitida(politica, tool)


def resumo_politica(politica: dict[str, Any]) -> dict[str, Any]:
    tools = sorted(politica.get("tools") or [])
    return {
        "perfil_slug": politica.get("perfil_slug"),
        "perfil_nome": politica.get("perfil_nome"),
        "modelo_orquestrador": politica.get("modelo_orquestrador"),
        "modelo_redator": politica.get("modelo_redator"),
        "fonte": politica.get("fonte"),
        "bypass": bool(politica.get("bypass")),
        "tools_count": len(tools),
        "tools": tools,
        "campanha_id": politica.get("campanha_id"),
    }
