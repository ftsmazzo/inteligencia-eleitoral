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
    query: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limite or 50), 200))
    q = (query or "").strip()
    like = f"%{q}%" if q else None
    if tipo and like:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid AND tipo = %s
              AND (titulo ILIKE %s OR corpo ILIKE %s)
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, tipo, like, like, lim),
        ).fetchall()
    elif like:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid
              AND (titulo ILIKE %s OR corpo ILIKE %s)
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, like, like, lim),
        ).fetchall()
    elif tipo:
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
                WHEN 'base_mapa_cargo' THEN 5
                WHEN 'base_prefeitos' THEN 6
                WHEN 'base_ficha_uf' THEN 7
                WHEN 'base_redes' THEN 8
                WHEN 'base_eleitorado' THEN 9
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


def texto_escopo_para_apura(
    status: dict[str, Any] | None,
    radar_cfg: dict[str, Any] | None = None,
) -> str:
    """Bloco fixo de identidade da campanha — sempre no topo do contexto do Apura.

    Existe pra resolver um bug concreto: o chat perguntava "ano/cargo/UF/candidato"
    de novo mesmo com o escopo já salvo na Gestão, porque só a memória indexada
    (campanha_memoria) chegava ao prompt — não o escopo (ctl.campanha) nem o
    Radar (ctl.radar_config). Isso injeta os dois, com prioridade pro escopo.
    """
    status = status or {}
    radar_cfg = radar_cfg or {}
    nome = status.get("nm_urna") or status.get("nm_candidato") or radar_cfg.get("candidato_nome")
    uf = status.get("sg_uf") or radar_cfg.get("uf")
    cargo = status.get("cargo_label") or radar_cfg.get("cargo")
    ano = status.get("ano_ref")
    partido = status.get("sg_partido")
    sq = status.get("sq_candidato")
    if not (nome or uf or cargo):
        return ""
    linhas = [
        "ESCOPO DA CAMPANHA (já configurado nesta conta — NUNCA pergunte de novo "
        "ano/cargo/UF/candidato; use direto pra responder e pra filtrar tools):"
    ]
    if nome:
        linhas.append(f"- Candidato monitorado (o \"nosso\" desta campanha): {nome}" + (f" ({partido})" if partido else ""))
    if cargo:
        linhas.append(f"- Cargo: {cargo}")
    if uf:
        linhas.append(f"- UF: {uf}")
    if ano:
        linhas.append(f"- Ano de referência: {ano}")
    if sq:
        linhas.append(f"- sq_candidato (TSE): {sq}")
    linhas.append(
        "Perguntas do tipo \"quem é nosso candidato\", \"qual nosso cargo/UF/ano\" — "
        "responda direto com os dados acima, sem chamar tool e sem PENDENTE."
    )
    return "\n".join(linhas)


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
