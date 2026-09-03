"""Usuários da equipe da campanha (coordenador gera logins)."""
from __future__ import annotations

import re
import secrets
import uuid
from typing import Any

import psycopg

from apura.auth import gerar_mcp_token, hash_senha

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOOTSTRAP_EMAIL = "leonardotamburus@gmail.com"
BOOTSTRAP_NOME = "Leonardo Tamburus"
# Senha inicial só na 1ª criação; o coordenador pode redefinir na tela de equipe.
BOOTSTRAP_SENHA = "ApuraGestao2026"


def _ok_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.match(e) or len(e) > 160:
        raise ValueError("E-mail inválido")
    return e


def listar(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id::text, email, COALESCE(nome, ''), COALESCE(papel, 'equipe'),
               COALESCE(ativo, true), quota_perguntas_max, quota_perguntas_used
        FROM ctl.apura_usuario
        WHERE campanha_id = %s::uuid
        ORDER BY
          CASE COALESCE(papel, 'equipe') WHEN 'coordenador' THEN 0 ELSE 1 END,
          email
        """,
        (campanha_id,),
    ).fetchall()
    out = []
    for r in rows:
        qmax = r[5]
        out.append(
            {
                "id": r[0],
                "email": r[1],
                "nome": r[2],
                "papel": r[3],
                "ativo": bool(r[4]),
                "quota_ilimitada": qmax is None,
                "quota_max": qmax,
                "quota_used": int(r[6] or 0),
            }
        )
    return out


def criar(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    email: str,
    nome: str = "",
    papel: str = "equipe",
    senha: str | None = None,
) -> dict[str, Any]:
    email = _ok_email(email)
    papel = (papel or "equipe").strip().lower()
    if papel not in ("coordenador", "equipe"):
        raise ValueError("Papel deve ser coordenador ou equipe")
    existe = conn.execute(
        "SELECT id::text FROM ctl.apura_usuario WHERE lower(email) = %s",
        (email,),
    ).fetchone()
    if existe:
        raise ValueError("E-mail já cadastrado")
    senha_plain = (senha or "").strip() or secrets.token_urlsafe(10)
    if len(senha_plain) < 8:
        raise ValueError("Senha com no mínimo 8 caracteres")
    uid = str(uuid.uuid4())
    mcp = gerar_mcp_token()
    display = (nome or "").strip() or email.split("@")[0]
    conn.execute(
        """
        INSERT INTO ctl.apura_usuario (
          id, email, nome, senha_hash, mcp_token, campanha_id, papel,
          quota_perguntas_max, quota_perguntas_used, ativo
        )
        VALUES (%s::uuid, %s, %s, %s, %s, %s::uuid, %s, NULL, 0, TRUE)
        """,
        (uid, email, display, hash_senha(senha_plain), mcp, campanha_id, papel),
    )
    conn.execute(
        """
        INSERT INTO ctl.mcp_token (token, rotulo, nome, email, campanha_id, apura_usuario_id, quota_max, quota_used)
        VALUES (%s, %s, %s, %s, %s::uuid, %s::uuid, NULL, 0)
        ON CONFLICT (token) DO NOTHING
        """,
        (mcp, f"apura:{email}", display, email, campanha_id, uid),
    )
    return {
        "id": uid,
        "email": email,
        "nome": display,
        "papel": papel,
        "senha_temporaria": senha_plain,
        "aviso": "Anote a senha agora — não será exibida de novo. Peça ao usuário para entrar em /apura/app.",
    }


def redefinir_senha(conn: psycopg.Connection, campanha_id: str, usuario_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id::text, email FROM ctl.apura_usuario
        WHERE id = %s::uuid AND campanha_id = %s::uuid
        """,
        (usuario_id, campanha_id),
    ).fetchone()
    if not row:
        raise ValueError("Usuário não encontrado nesta campanha")
    senha = secrets.token_urlsafe(10)
    conn.execute(
        "UPDATE ctl.apura_usuario SET senha_hash = %s WHERE id = %s::uuid",
        (hash_senha(senha), usuario_id),
    )
    return {"id": row[0], "email": row[1], "senha_temporaria": senha}


def set_ativo(
    conn: psycopg.Connection, campanha_id: str, usuario_id: str, ativo: bool
) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE ctl.apura_usuario
        SET ativo = %s
        WHERE id = %s::uuid AND campanha_id = %s::uuid
        RETURNING id::text, email, ativo
        """,
        (ativo, usuario_id, campanha_id),
    ).fetchone()
    if not row:
        raise ValueError("Usuário não encontrado nesta campanha")
    return {"id": row[0], "email": row[1], "ativo": bool(row[2])}


def garantir_bootstrap(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any] | None:
    """Garante o coordenador combinado (Leonardo) nesta campanha — idempotente.

    Se o e-mail já existe: promove a coordenador, cola na campanha, quota ilimitada.
    Se não existe: cria com senha inicial BOOTSTRAP_SENHA (única vez).
    """
    email = BOOTSTRAP_EMAIL
    row = conn.execute(
        "SELECT id::text, campanha_id::text, COALESCE(papel,'equipe') FROM ctl.apura_usuario WHERE lower(email) = %s",
        (email,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE ctl.apura_usuario
            SET campanha_id = %s::uuid,
                papel = 'coordenador',
                quota_perguntas_max = NULL,
                ativo = TRUE,
                nome = COALESCE(NULLIF(nome, ''), %s)
            WHERE id = %s::uuid
            """,
            (campanha_id, BOOTSTRAP_NOME, row[0]),
        )
        return {"email": email, "id": row[0], "criado": False, "promovido": True}
    criou = criar(
        conn,
        campanha_id,
        email=email,
        nome=BOOTSTRAP_NOME,
        papel="coordenador",
        senha=BOOTSTRAP_SENHA,
    )
    criou["criado"] = True
    criou["promovido"] = False
    return criou
