"""Skills pessoais do usuário (instruções para o redator expert)."""
from __future__ import annotations

import uuid
from typing import Any

import psycopg
from fastapi import HTTPException

MAX_SKILLS = 20
MAX_ATIVAS = 3
MAX_NOME = 80
MAX_CONTEUDO = 8000


def _contar_ativas(conn: psycopg.Connection, usuario_id: str, exceto_id: str | None = None) -> int:
    if exceto_id:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM ctl.apura_skill
            WHERE usuario_id = %s::uuid AND ativo IS TRUE AND id <> %s::uuid
            """,
            (usuario_id, exceto_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM ctl.apura_skill WHERE usuario_id = %s::uuid AND ativo IS TRUE",
            (usuario_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def listar_skills(conn: psycopg.Connection, usuario_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id::text, nome, conteudo, ativo, criado_em, atualizado_em
        FROM ctl.apura_skill
        WHERE usuario_id = %s::uuid
        ORDER BY ativo DESC, atualizado_em DESC
        """,
        (usuario_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "nome": r[1],
            "conteudo": r[2],
            "ativo": r[3],
            "criado_em": r[4].isoformat(),
            "atualizado_em": r[5].isoformat(),
        }
        for r in rows
    ]


def texto_skills_ativas(conn: psycopg.Connection, usuario_id: str) -> str:
    rows = conn.execute(
        """
        SELECT nome, conteudo FROM ctl.apura_skill
        WHERE usuario_id = %s::uuid AND ativo IS TRUE
        ORDER BY atualizado_em DESC
        LIMIT %s
        """,
        (usuario_id, MAX_ATIVAS),
    ).fetchall()
    if not rows:
        return ""
    partes = []
    for nome, conteudo in rows:
        partes.append(f"### Skill: {nome}\n{conteudo.strip()}")
    return "\n\n".join(partes)


def criar_skill(conn: psycopg.Connection, usuario_id: str, nome: str, conteudo: str, ativo: bool = False) -> dict[str, Any]:
    total = conn.execute(
        "SELECT COUNT(*) FROM ctl.apura_skill WHERE usuario_id = %s::uuid",
        (usuario_id,),
    ).fetchone()[0]
    if total >= MAX_SKILLS:
        raise HTTPException(400, f"Máximo de {MAX_SKILLS} skills por usuário")
    if ativo and _contar_ativas(conn, usuario_id) >= MAX_ATIVAS:
        raise HTTPException(400, f"Máximo de {MAX_ATIVAS} skills ativas simultâneas")
    sid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO ctl.apura_skill (id, usuario_id, nome, conteudo, ativo)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s)
        """,
        (sid, usuario_id, nome.strip(), conteudo.strip(), ativo),
    )
    return {"id": sid, "nome": nome.strip(), "ativo": ativo}


def atualizar_skill(
    conn: psycopg.Connection,
    usuario_id: str,
    skill_id: str,
    nome: str | None = None,
    conteudo: str | None = None,
    ativo: bool | None = None,
) -> None:
    ok = conn.execute(
        "SELECT 1 FROM ctl.apura_skill WHERE id = %s::uuid AND usuario_id = %s::uuid",
        (skill_id, usuario_id),
    ).fetchone()
    if not ok:
        raise HTTPException(404, "Skill não encontrada")
    if ativo is True and _contar_ativas(conn, usuario_id, exceto_id=skill_id) >= MAX_ATIVAS:
        raise HTTPException(400, f"Máximo de {MAX_ATIVAS} skills ativas simultâneas")
    sets: list[str] = ["atualizado_em = now()"]
    params: list[Any] = []
    if nome is not None:
        sets.append("nome = %s")
        params.append(nome.strip())
    if conteudo is not None:
        sets.append("conteudo = %s")
        params.append(conteudo.strip())
    if ativo is not None:
        sets.append("ativo = %s")
        params.append(ativo)
    params.extend([skill_id, usuario_id])
    conn.execute(
        f"UPDATE ctl.apura_skill SET {', '.join(sets)} WHERE id = %s::uuid AND usuario_id = %s::uuid",
        params,
    )


def deletar_skill(conn: psycopg.Connection, usuario_id: str, skill_id: str) -> None:
    cur = conn.execute(
        "DELETE FROM ctl.apura_skill WHERE id = %s::uuid AND usuario_id = %s::uuid RETURNING id",
        (skill_id, usuario_id),
    ).fetchone()
    if not cur:
        raise HTTPException(404, "Skill não encontrada")
