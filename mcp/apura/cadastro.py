"""Cadastro auto-aprovado Apura: token MCP + conta vinculada à campanha."""
from __future__ import annotations

import secrets
import uuid
from typing import Any

import psycopg
from fastapi import HTTPException

from apura.auth import registrar_usuario


def emitir_mcp_token(
    conn: psycopg.Connection,
    nome: str,
    email: str,
    telefone: str,
    campanha_id: str,
) -> str:
    """Insere linha em ctl.mcp_token; retorna token gerado."""
    email = email.strip().lower()
    token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO ctl.mcp_token (token, rotulo, nome, email, telefone, campanha_id)
        VALUES (%s, %s, %s, %s, %s, %s::uuid)
        """,
        (token, f"pessoa:{email}", nome.strip(), email, (telefone or "").strip(), campanha_id),
    )
    return token


def _email_em_uso(conn: psycopg.Connection, email: str) -> bool:
    if conn.execute(
        """
        SELECT 1 FROM ctl.mcp_token
        WHERE lower(email) = lower(%s)
        LIMIT 1
        """,
        (email,),
    ).fetchone():
        return True
    if conn.execute(
        """
        SELECT 1 FROM ctl.apura_usuario
        WHERE lower(email) = lower(%s)
        LIMIT 1
        """,
        (email,),
    ).fetchone():
        return True
    return False


def listar_campanhas_ativas(conn: psycopg.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT nome, COALESCE(NULLIF(nome, ''), nome)
        FROM ctl.campanha
        WHERE ativo IS TRUE
        ORDER BY nome
        """
    ).fetchall()
    return [{"nome": r[0], "rotulo": r[1]} for r in rows]


def solicitar_cadastro(
    conn: psycopg.Connection,
    nome: str,
    email: str,
    telefone: str,
    campanha_nome: str,
) -> dict[str, Any]:
    """Auto-aprova: mcp_token + apura_usuario + log em cadastro_request."""
    email = email.strip().lower()
    nome = nome.strip()
    campanha_nome = campanha_nome.strip()

    if len(nome) < 2:
        raise HTTPException(400, "Informe seu nome")
    if _email_em_uso(conn, email):
        raise HTTPException(409, "E-mail já cadastrado")

    camp = conn.execute(
        """
        SELECT id::text FROM ctl.campanha
        WHERE nome = %s AND ativo IS TRUE
        """,
        (campanha_nome,),
    ).fetchone()
    if not camp:
        raise HTTPException(400, "Campanha não existe")

    campanha_id = camp[0]
    request_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO ctl.cadastro_request (id, email, nome, telefone, campanha_id, status)
        VALUES (%s::uuid, %s, %s, %s, %s::uuid, 'pendente')
        """,
        (request_id, email, nome, (telefone or "").strip() or None, campanha_id),
    )

    try:
        token = emitir_mcp_token(conn, nome, email, telefone, campanha_id)
        registrar_usuario(conn, email, token, nome)
        conn.execute(
            """
            UPDATE ctl.cadastro_request
            SET status = 'aprovado',
                token_gerado = %s,
                aprovado_em = now()
            WHERE id = %s::uuid
            """,
            (token, request_id),
        )
    except HTTPException:
        conn.execute(
            """
            UPDATE ctl.cadastro_request SET status = 'recusado'
            WHERE id = %s::uuid
            """,
            (request_id,),
        )
        raise
    except Exception as exc:
        conn.execute(
            """
            UPDATE ctl.cadastro_request SET status = 'recusado'
            WHERE id = %s::uuid
            """,
            (request_id,),
        )
        raise HTTPException(503, f"Falha ao concluir cadastro: {type(exc).__name__}") from exc

    return {
        "status": "ok",
        "message": "Cadastro aprovado. Seu token será mostrado uma vez.",
        "request_id": request_id,
    }


def entregar_token(conn: psycopg.Connection, request_id: str) -> str:
    """Retorna token uma única vez (não reexibe depois)."""
    row = conn.execute(
        """
        SELECT token_gerado, status, token_entregue
        FROM ctl.cadastro_request
        WHERE id = %s::uuid
        """,
        (request_id,),
    ).fetchone()
    if not row or row[1] != "aprovado" or not row[0]:
        raise HTTPException(404, "Solicitação não encontrada ou não aprovada")
    if row[2]:
        raise HTTPException(410, "Token já foi exibido. Use o e-mail de confirmação ou peça novo acesso.")
    conn.execute(
        """
        UPDATE ctl.cadastro_request SET token_entregue = TRUE
        WHERE id = %s::uuid
        """,
        (request_id,),
    )
    return row[0]
