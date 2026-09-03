"""Memória indexada da campanha (ctl.campanha_memoria)."""
from __future__ import annotations

import json
from typing import Any

import psycopg


def limpar_tipos(conn: psycopg.Connection, campanha_id: str, tipos: list[str]) -> None:
    if not tipos:
        return
    conn.execute(
        """
        DELETE FROM ctl.campanha_memoria
        WHERE campanha_id = %s::uuid AND tipo = ANY(%s)
        """,
        (campanha_id, tipos),
    )


def upsert_bloco(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    tipo: str,
    titulo: str,
    corpo: str,
    fonte: str = "",
    nivel: str = "indicio",
    meta: dict[str, Any] | None = None,
) -> str:
    row = conn.execute(
        """
        INSERT INTO ctl.campanha_memoria
          (campanha_id, tipo, titulo, corpo, fonte, nivel, meta_json)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id::text
        """,
        (
            campanha_id,
            tipo,
            (titulo or "")[:300],
            corpo or "",
            fonte or "",
            nivel or "indicio",
            json.dumps(meta or {}, ensure_ascii=False),
        ),
    ).fetchone()
    return row[0] if row else ""


def listar(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    tipo: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limite or 50), 200))
    if tipo:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid AND tipo = %s
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, tipo, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid
            ORDER BY
              CASE tipo
                WHEN 'perfil_eleitor' THEN 1
                WHEN 'base_trajetoria' THEN 2
                WHEN 'base_concorrentes' THEN 3
                WHEN 'base_votos' THEN 4
                WHEN 'base_prefeitos' THEN 5
                WHEN 'base_redes' THEN 6
                ELSE 10
              END,
              criado_em DESC
            LIMIT %s
            """,
            (campanha_id, lim),
        ).fetchall()
    out = []
    for r in rows:
        meta = r[6] if isinstance(r[6], dict) else (json.loads(r[6]) if r[6] else {})
        out.append(
            {
                "id": r[0],
                "tipo": r[1],
                "titulo": r[2],
                "corpo": r[3],
                "fonte": r[4],
                "nivel": r[5],
                "meta": meta,
                "criado_em": r[7].isoformat() if r[7] else None,
            }
        )
    return out


def texto_para_apura(conn: psycopg.Connection, campanha_id: str, *, max_chars: int = 12000) -> str:
    """Concatena blocos prioritários para o system prompt do Apura."""
    blocos = listar(conn, campanha_id, limite=40)
    if not blocos:
        return ""
    partes: list[str] = [
        "CONHECIMENTO DA CAMPANHA (memória indexada — contextualiza; cifras oficiais vêm das tools):"
    ]
    used = len(partes[0])
    for b in blocos:
        chunk = f"\n### [{b['tipo']}] {b['titulo']}\n{b['corpo']}\n(fonte: {b['fonte'] or 'campanha'} | nível: {b['nivel']})"
        if used + len(chunk) > max_chars:
            break
        partes.append(chunk)
        used += len(chunk)
    return "\n".join(partes)
