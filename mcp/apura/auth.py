"""Autenticação JWT e senhas do Apura."""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import psycopg

_ALGO = "HS256"
_TTL_DAYS = 14


def _secret() -> str:
    s = os.environ.get("APURA_JWT_SECRET") or os.environ.get("MCP_TOKEN", "")
    if not s:
        raise ValueError("APURA_JWT_SECRET não configurado")
    return s


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))


def criar_token_jwt(usuario_id: str, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS)
    token = jwt.encode(
        {"sub": usuario_id, "email": email, "exp": exp},
        _secret(),
        algorithm=_ALGO,
    )
    return token if isinstance(token, str) else token.decode("utf-8")


def decodificar_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGO])
    except (jwt.PyJWTError, ValueError) as exc:
        from fastapi import HTTPException
        raise HTTPException(401, "Sessão inválida ou expirada") from exc


def gerar_mcp_token() -> str:
    return secrets.token_urlsafe(32)


def registrar_usuario(conn: psycopg.Connection, email: str, senha: str, nome: str) -> dict[str, str]:
    email = email.strip().lower()
    mcp_tok = gerar_mcp_token()
    uid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO ctl.apura_usuario (id, email, nome, senha_hash, mcp_token)
        VALUES (%s::uuid, %s, %s, %s, %s)
        """,
        (uid, email, nome.strip(), hash_senha(senha), mcp_tok),
    )
    conn.execute(
        "INSERT INTO ctl.mcp_token (token, rotulo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (mcp_tok, f"apura:{email}"),
    )
    return {"id": uid, "email": email, "token": criar_token_jwt(uid, email)}


def login_usuario(conn: psycopg.Connection, email: str, senha: str) -> dict[str, str]:
    from fastapi import HTTPException
    row = conn.execute(
        """
        SELECT id::text, email, senha_hash, nome
        FROM ctl.apura_usuario
        WHERE email = %s AND ativo IS TRUE
        """,
        (email.strip().lower(),),
    ).fetchone()
    if not row or not verificar_senha(senha, row[2]):
        raise HTTPException(401, "E-mail ou senha incorretos")
    return {
        "id": row[0],
        "email": row[1],
        "nome": row[3],
        "token": criar_token_jwt(row[0], row[1]),
    }


def usuario_por_id(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str, str]:
    from fastapi import HTTPException
    row = conn.execute(
        "SELECT id::text, email, mcp_token FROM ctl.apura_usuario WHERE id = %s AND ativo IS TRUE",
        (usuario_id,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Usuário não encontrado")
    return row[0], row[1], row[2]
