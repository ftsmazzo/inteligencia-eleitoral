"""Documento canônico do candidato na Trilha A (eleicao.candidatura)."""
from __future__ import annotations

from typing import Any

import psycopg


def por_sq(conn: psycopg.Connection, *, ano: int, sq_candidato: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.ano, c.cd_cargo, r.nome AS cargo, c.sg_uf, c.sq_candidato, c.nr_candidato,
               c.nm_urna, c.nm_candidato, c.sg_partido, c.ds_situacao, c.cd_municipio_tse
        FROM eleicao.candidatura c
        JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
        WHERE c.ano = %s AND c.sq_candidato = %s
        LIMIT 1
        """,
        (ano, sq_candidato),
    ).fetchone()
    if not row:
        return None
    return {
        "ano": int(row[0]),
        "cd_cargo": int(row[1]),
        "cargo": row[2],
        "sg_uf": row[3],
        "sq_candidato": int(row[4]),
        "nr_candidato": row[5],
        "nm_urna": row[6] or "",
        "nm_candidato": row[7] or "",
        "sg_partido": row[8] or "",
        "ds_situacao": row[9],
        "cd_municipio_tse": row[10],
    }


def historico_mesmo_nome(
    conn: psycopg.Connection,
    *,
    nm_urna: str,
    nm_candidato: str,
    uf: str | None,
    limite: int = 12,
) -> list[dict[str, Any]]:
    """Candidaturas do mesmo nome civil/urna (match exato) — para exibir no cartão."""
    urna = (nm_urna or "").strip()
    civil = (nm_candidato or "").strip()
    if not urna and not civil:
        return []
    params: list[Any] = []
    clauses = []
    if urna:
        clauses.append("upper(c.nm_urna) = upper(%s)")
        params.append(urna)
    if civil:
        clauses.append("upper(c.nm_candidato) = upper(%s)")
        params.append(civil)
    where_nome = "(" + " OR ".join(clauses) + ")"
    uf_sql = ""
    if uf:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)
    params.append(limite)
    rows = conn.execute(
        f"""
        SELECT c.ano, c.cd_cargo, r.nome, c.sg_partido, c.ds_situacao, c.sq_candidato, c.nr_candidato
        FROM eleicao.candidatura c
        JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
        WHERE {where_nome}
          {uf_sql}
          AND c.ano IN (2014, 2016, 2018, 2020, 2022, 2024, 2026)
        ORDER BY c.ano DESC, c.cd_cargo
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [
        {
            "ano": int(r[0]),
            "cd_cargo": int(r[1]),
            "cargo": r[2],
            "sg_partido": r[3],
            "ds_situacao": r[4],
            "sq_candidato": int(r[5]),
            "nr_candidato": r[6],
        }
        for r in rows
    ]


def enriquecer_linha(conn: psycopg.Connection, ln: dict[str, Any], *, ano: int) -> dict[str, Any]:
    sq = ln.get("sq_candidato")
    if not sq:
        return ln
    doc = por_sq(conn, ano=ano, sq_candidato=int(sq))
    if not doc:
        return ln
    out = dict(ln)
    out.update(
        {
            "nm_urna": doc["nm_urna"] or ln.get("nm_urna"),
            "nm_candidato": doc["nm_candidato"] or ln.get("nm_candidato"),
            "sg_partido": doc["sg_partido"] or ln.get("sg_partido"),
            "nr_candidato": doc["nr_candidato"] if doc["nr_candidato"] is not None else ln.get("nr_candidato"),
            "ds_situacao": doc["ds_situacao"] or ln.get("ds_situacao"),
            "documento_ok": True,
        }
    )
    hist = historico_mesmo_nome(
        conn,
        nm_urna=out.get("nm_urna") or "",
        nm_candidato=out.get("nm_candidato") or "",
        uf=out.get("sg_uf"),
        limite=8,
    )
    out["historico_resumo"] = [
        f"{h['ano']} {h['cargo']} ({h['sg_partido']})" for h in hist if int(h["ano"]) < int(ano)
    ][:5]
    return out
