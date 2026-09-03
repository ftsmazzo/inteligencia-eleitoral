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


def senha_amigavel() -> str:
    """Senha legível para equipe: Apura + 4 dígitos + letra (ex.: Apura4821k)."""
    n = secrets.randbelow(9000) + 1000
    letra = secrets.choice("abcdefghkmnpqrstuvwxyz")
    return f"Apura{n}{letra}"


def alterar_senha(
    conn: psycopg.Connection,
    usuario_id: str,
    senha_atual: str,
    senha_nova: str,
) -> dict[str, str]:
    from fastapi import HTTPException

    senha_nova = (senha_nova or "").strip()
    if len(senha_nova) < 8:
        raise HTTPException(400, "Nova senha com no mínimo 8 caracteres")
    if len(senha_nova) > 128:
        raise HTTPException(400, "Nova senha muito longa")
    if senha_nova == (senha_atual or "").strip():
        raise HTTPException(400, "A nova senha deve ser diferente da atual")
    row = conn.execute(
        """
        SELECT senha_hash FROM ctl.apura_usuario
        WHERE id = %s::uuid AND ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Usuário não encontrado")
    if not verificar_senha(senha_atual or "", row[0]):
        raise HTTPException(401, "Senha atual incorreta")
    conn.execute(
        "UPDATE ctl.apura_usuario SET senha_hash = %s WHERE id = %s::uuid",
        (hash_senha(senha_nova), usuario_id),
    )
    return {"status": "ok", "aviso": "Senha alterada. Use a nova senha no próximo login."}


def _demo_quota() -> int:
    raw = os.environ.get("DEMO_QUOTA", "5").strip()
    try:
        n = int(raw)
    except ValueError:
        return 5
    return max(1, min(n, 100))


def _token_precadastrado(
    conn: psycopg.Connection, email: str
) -> tuple[str, str | None, str | None] | None:
    """Token MCP pré-emitido (cadastrar_pessoa) ainda sem apura_usuario."""
    row = conn.execute(
        """
        SELECT token, campanha_id::text, nome
        FROM ctl.mcp_token
        WHERE lower(email) = lower(%s)
          AND apura_usuario_id IS NULL
          AND ativo IS TRUE
        ORDER BY criado_em DESC
        LIMIT 1
        FOR UPDATE
        """,
        (email,),
    ).fetchone()
    if not row:
        return None
    return row[0], row[1], row[2]


def registrar_usuario(conn: psycopg.Connection, email: str, senha: str, nome: str) -> dict[str, str]:
    from fastapi import HTTPException

    email = email.strip().lower()
    existe = conn.execute(
        "SELECT 1 FROM ctl.apura_usuario WHERE lower(email) = %s",
        (email,),
    ).fetchone()
    if existe:
        raise HTTPException(409, "E-mail já cadastrado")

    precad = _token_precadastrado(conn, email)
    uid = str(uuid.uuid4())
    quota = _demo_quota()
    display_nome = nome.strip() or (precad[2] if precad and precad[2] else "")

    if precad:
        mcp_tok, campanha_id, _ = precad
        if not campanha_id:
            raise HTTPException(
                400,
                "Token pré-cadastrado sem campanha. Peça novo acesso à equipe.",
            )
        conn.execute(
            """
            INSERT INTO ctl.apura_usuario (
              id, email, nome, senha_hash, mcp_token, campanha_id,
              quota_perguntas_max, quota_perguntas_used
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s::uuid, %s, 0)
            """,
            (
                uid,
                email,
                display_nome,
                hash_senha(senha),
                mcp_tok,
                campanha_id,
                quota,
            ),
        )
        conn.execute(
            """
            UPDATE ctl.mcp_token
            SET apura_usuario_id = %s::uuid,
                nome = COALESCE(NULLIF(nome, ''), %s),
                email = COALESCE(email, %s)
            WHERE token = %s
            """,
            (uid, display_nome, email, mcp_tok),
        )
    else:
        mcp_tok = gerar_mcp_token()
        campanha_row = conn.execute(
            "SELECT id::text FROM ctl.campanha WHERE nome = %s AND ativo IS TRUE",
            ("governador-amapa",),
        ).fetchone()
        if not campanha_row:
            raise HTTPException(503, "Campanha padrão indisponível")
        conn.execute(
            """
            INSERT INTO ctl.apura_usuario (
              id, email, nome, senha_hash, mcp_token, campanha_id,
              quota_perguntas_max, quota_perguntas_used
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s::uuid, %s, 0)
            """,
            (
                uid,
                email,
                display_nome,
                hash_senha(senha),
                mcp_tok,
                campanha_row[0],
                quota,
            ),
        )
        conn.execute(
            """
            INSERT INTO ctl.mcp_token (token, rotulo, nome, email, campanha_id, apura_usuario_id, quota_max, quota_used)
            VALUES (%s, %s, %s, %s, %s::uuid, %s::uuid, NULL, 0)
            ON CONFLICT (token) DO NOTHING
            """,
            (mcp_tok, f"apura:{email}", display_nome, email, campanha_row[0], uid),
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


def quota_usuario(conn: psycopg.Connection, usuario_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT quota_perguntas_max, quota_perguntas_used
        FROM ctl.apura_usuario
        WHERE id = %s::uuid AND ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row:
        return {"ilimitado": True, "max": None, "used": 0, "restantes": None}
    qmax, used = row[0], int(row[1] or 0)
    if qmax is None:
        return {"ilimitado": True, "max": None, "used": used, "restantes": None}
    return {
        "ilimitado": False,
        "max": int(qmax),
        "used": used,
        "restantes": max(0, int(qmax) - used),
    }


def consumir_pergunta_demo(conn: psycopg.Connection, usuario_id: str) -> dict[str, Any]:
    """Consome 1 pergunta do demo. Levanta 429 se esgotado."""
    from fastapi import HTTPException

    row = conn.execute(
        """
        SELECT quota_perguntas_max, quota_perguntas_used
        FROM ctl.apura_usuario
        WHERE id = %s::uuid AND ativo IS TRUE
        FOR UPDATE
        """,
        (usuario_id,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Usuário não encontrado")
    qmax, used = row[0], int(row[1] or 0)
    if qmax is None:
        return {"ilimitado": True, "max": None, "used": used, "restantes": None}
    if used >= int(qmax):
        raise HTTPException(
            429,
            f"Cota demo esgotada ({qmax} perguntas). Fale com a equipe para liberar acesso comercial.",
        )
    conn.execute(
        """
        UPDATE ctl.apura_usuario
        SET quota_perguntas_used = quota_perguntas_used + 1
        WHERE id = %s::uuid
        """,
        (usuario_id,),
    )
    novo = used + 1
    return {
        "ilimitado": False,
        "max": int(qmax),
        "used": novo,
        "restantes": max(0, int(qmax) - novo),
    }
