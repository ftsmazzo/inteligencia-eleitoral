"""CRUD store do Radar (filtrado por campanha_id uuid)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

BRT = ZoneInfo("America/Sao_Paulo")

DEFAULT_EIXOS = [
    ("Gestao e entregas", "obras, servicos, saude, educacao, resultado de governo"),
    ("Territorio e interior", "cidade, municipio, visita, interior, bairro"),
    ("Enfrentamento", "adversario, denuncia, contraste, resposta a ataque"),
    ("Identidade", "trajetoria, valores, biografia, fe, familia"),
    ("Mobilizacao", "voto, urna, afiliacao, adesao, evento de campanha"),
]


def fingerprint(campanha_id: str, url: str | None, titulo: str) -> str:
    raw = f"{campanha_id}|{url or ''}|{titulo or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fmt_brt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime("%d/%m %H:%M")


def ensure_eixos(conn: psycopg.Connection, campanha_id: str) -> None:
    for name, hint in DEFAULT_EIXOS:
        conn.execute(
            """
            INSERT INTO ctl.radar_eixo (campanha_id, name, hint, enabled)
            VALUES (%s::uuid, %s, %s, TRUE)
            ON CONFLICT (campanha_id, name) DO NOTHING
            """,
            (campanha_id, name, hint),
        )


def list_eixos(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    ensure_eixos(conn, campanha_id)
    rows = conn.execute(
        """
        SELECT id::text, name, hint, enabled
        FROM ctl.radar_eixo
        WHERE campanha_id = %s::uuid
        ORDER BY name
        """,
        (campanha_id,),
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "hint": r[2], "enabled": bool(r[3])}
        for r in rows
    ]


def list_alvos(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    ativo_only: bool = True,
) -> list[dict[str, Any]]:
    q = """
        SELECT id::text, kind, nome, query_news, handle_ig, is_own, ativo,
               last_seen_at, criado_em
        FROM ctl.radar_alvo
        WHERE campanha_id = %s::uuid
    """
    if ativo_only:
        q += " AND ativo IS TRUE"
    q += " ORDER BY is_own DESC, kind, nome"
    rows = conn.execute(q, (campanha_id,)).fetchall()
    return [
        {
            "id": r[0],
            "kind": r[1],
            "nome": r[2],
            "query_news": r[3] or "",
            "handle_ig": r[4],
            "is_own": bool(r[5]),
            "ativo": bool(r[6]),
            "last_seen_at": r[7].isoformat() if r[7] else None,
            "criado_em": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]


def upsert_alvo(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    kind: str,
    nome: str,
    query_news: str = "",
    handle_ig: str | None = None,
    is_own: bool = False,
    ativo: bool = True,
    alvo_id: str | None = None,
) -> dict[str, Any]:
    kind = (kind or "pessoa").strip().lower()
    if kind not in ("pessoa", "tema", "perfil"):
        raise ValueError("kind invalido")
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("nome obrigatorio")
    handle = (handle_ig or "").strip().lstrip("@") or None
    qn = (query_news or nome).strip()
    if alvo_id:
        conn.execute(
            """
            UPDATE ctl.radar_alvo
            SET kind=%s, nome=%s, query_news=%s, handle_ig=%s, is_own=%s, ativo=%s
            WHERE id=%s::uuid AND campanha_id=%s::uuid
            """,
            (kind, nome, qn, handle, is_own, ativo, alvo_id, campanha_id),
        )
        aid = alvo_id
    else:
        row = conn.execute(
            """
            INSERT INTO ctl.radar_alvo (
              campanha_id, kind, nome, query_news, handle_ig, is_own, ativo
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
            RETURNING id::text
            """,
            (campanha_id, kind, nome, qn, handle, is_own, ativo),
        ).fetchone()
        aid = row[0]
    rows = list_alvos(conn, campanha_id, ativo_only=False)
    return next(a for a in rows if a["id"] == aid)


def delete_alvo(conn: psycopg.Connection, campanha_id: str, alvo_id: str) -> None:
    conn.execute(
        "DELETE FROM ctl.radar_alvo WHERE id=%s::uuid AND campanha_id=%s::uuid",
        (alvo_id, campanha_id),
    )


def mark_alvo_seen(conn: psycopg.Connection, alvo_id: str, when: datetime | None = None) -> None:
    conn.execute(
        "UPDATE ctl.radar_alvo SET last_seen_at=%s WHERE id=%s::uuid",
        (when or datetime.now(timezone.utc), alvo_id),
    )


def insert_item(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    origem: str,
    canal: str,
    fonte: str | None,
    url: str | None,
    titulo: str,
    body: str,
    published_at: datetime | None,
    entity_name: str | None,
) -> str | None:
    """Insere item se fingerprint novo. Retorna id ou None se duplicado."""
    pub = published_at or datetime.now(timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    fp = fingerprint(campanha_id, url, titulo)
    row = conn.execute(
        """
        INSERT INTO ctl.radar_item (
          campanha_id, origem, canal, fonte, url, titulo, body,
          published_at, fingerprint, entity_name
        )
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (campanha_id, fingerprint) DO NOTHING
        RETURNING id::text
        """,
        (
            campanha_id,
            origem if origem in ("clima", "oficial") else "clima",
            (canal or "news").strip().lower(),
            fonte,
            url,
            titulo.strip(),
            body or "",
            pub,
            fp,
            entity_name,
        ),
    ).fetchone()
    return row[0] if row else None


def save_analise(
    conn: psycopg.Connection,
    item_id: str,
    data: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO ctl.radar_analise (
          item_id, tipo, urgencia, polarity, score, risk, synthesis,
          eixo, model, action_respond
        )
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (item_id) DO UPDATE SET
          tipo=EXCLUDED.tipo,
          urgencia=EXCLUDED.urgencia,
          polarity=EXCLUDED.polarity,
          score=EXCLUDED.score,
          risk=EXCLUDED.risk,
          synthesis=EXCLUDED.synthesis,
          eixo=EXCLUDED.eixo,
          model=EXCLUDED.model,
          action_respond=EXCLUDED.action_respond
        """,
        (
            item_id,
            data.get("tipo"),
            data.get("urgencia"),
            data.get("polarity"),
            data.get("score"),
            data.get("risk"),
            data.get("synthesis"),
            data.get("eixo") or "",
            data.get("model") or data.get("_model"),
            data.get("action_respond"),
        ),
    )


def start_run(
    conn: psycopg.Connection,
    campanha_id: str | None,
    mode: str,
) -> str:
    row = conn.execute(
        """
        INSERT INTO ctl.radar_run (campanha_id, mode, ok)
        VALUES (%s::uuid, %s, 0)
        RETURNING id::text
        """,
        (campanha_id, mode),
    ).fetchone()
    return row[0]


def finish_run(
    conn: psycopg.Connection,
    run_id: str,
    *,
    ok: int,
    err: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ctl.radar_run
        SET ok=%s, err=%s, finished_at=now()
        WHERE id=%s::uuid
        """,
        (ok, err, run_id),
    )


def last_run(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id::text, mode, ok, err, started_at, finished_at
        FROM ctl.radar_run
        WHERE campanha_id = %s::uuid OR campanha_id IS NULL
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (campanha_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "mode": row[1],
        "ok": int(row[2] or 0),
        "err": row[3],
        "started_at": row[4].isoformat() if row[4] else None,
        "finished_at": row[5].isoformat() if row[5] else None,
        "started_brt": fmt_brt(row[4]),
    }


def kpi_24h(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    corte = datetime.now(timezone.utc) - timedelta(hours=24)
    row = conn.execute(
        """
        SELECT
          COUNT(*)::int,
          COALESCE(AVG(a.score) FILTER (WHERE i.origem = 'clima'), 0)::float,
          COUNT(*) FILTER (WHERE i.origem = 'clima')::int,
          COUNT(*) FILTER (WHERE i.origem = 'oficial')::int
        FROM ctl.radar_item i
        LEFT JOIN ctl.radar_analise a ON a.item_id = i.id
        WHERE i.campanha_id = %s::uuid
          AND i.published_at >= %s
        """,
        (campanha_id, corte),
    ).fetchone()
    alvos = conn.execute(
        """
        SELECT COUNT(*)::int,
               COUNT(*) FILTER (WHERE kind = 'perfil')::int
        FROM ctl.radar_alvo
        WHERE campanha_id = %s::uuid AND ativo IS TRUE
        """,
        (campanha_id,),
    ).fetchone()
    return {
        "itens_24h": int(row[0] or 0),
        "score_medio_clima": round(float(row[1] or 0), 1),
        "clima_24h": int(row[2] or 0),
        "oficial_24h": int(row[3] or 0),
        "alvos": int(alvos[0] or 0),
        "perfis": int(alvos[1] or 0),
    }


def stream(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    q: str | None = None,
    canal: str | None = None,
    origem: str | None = None,
    tipo: str | None = None,
    urgencia: str | None = None,
    janela_horas: int | None = 168,
    page: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    lim = max(1, min(int(limite or 20), 50))
    pg = max(1, int(page or 1))
    offset = (pg - 1) * lim
    where = ["i.campanha_id = %s::uuid"]
    params: list[Any] = [campanha_id]

    if janela_horas and janela_horas > 0:
        where.append("i.published_at >= %s")
        params.append(datetime.now(timezone.utc) - timedelta(hours=janela_horas))
    if canal:
        where.append("lower(i.canal) = %s")
        params.append(canal.strip().lower())
    if origem:
        where.append("i.origem = %s")
        params.append(origem.strip().lower())
    if tipo:
        where.append("lower(COALESCE(a.tipo, '')) = %s")
        params.append(tipo.strip().lower())
    if urgencia:
        where.append("lower(COALESCE(a.urgencia, '')) = %s")
        params.append(urgencia.strip().lower())
    if q:
        where.append(
            "(i.titulo ILIKE %s OR i.body ILIKE %s OR COALESCE(i.entity_name,'') ILIKE %s)"
        )
        like = f"%{q.strip()}%"
        params.extend([like, like, like])

    wsql = " AND ".join(where)
    total = conn.execute(
        f"""
        SELECT COUNT(*)::int
        FROM ctl.radar_item i
        LEFT JOIN ctl.radar_analise a ON a.item_id = i.id
        WHERE {wsql}
        """,
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT i.id::text, i.origem, i.canal, i.fonte, i.url, i.titulo, i.body,
               i.published_at, i.entity_name,
               a.tipo, a.urgencia, a.polarity, a.score, a.risk, a.synthesis,
               a.eixo, a.model, a.action_respond
        FROM ctl.radar_item i
        LEFT JOIN ctl.radar_analise a ON a.item_id = i.id
        WHERE {wsql}
        ORDER BY i.published_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [lim, offset],
    ).fetchall()

    itens: list[dict[str, Any]] = []
    for r in rows:
        quando = fmt_brt(r[7])
        fonte = r[3]
        itens.append(
            {
                "id": r[0],
                "origem": r[1],
                "canal": r[2],
                "fonte": fonte,
                "url": r[4],
                "titulo": r[5],
                "body": r[6],
                "published_at": r[7].isoformat() if r[7] else None,
                "quando": quando,
                "data_hora": quando,
                "rotulo": " · ".join(p for p in (fonte, quando) if p) or None,
                "alvo": r[8],
                "entity_name": r[8],
                "tipo": r[9],
                "urgencia": r[10],
                "tom": r[11],
                "polarity": r[11],
                "clima_score": r[12],
                "score": r[12],
                "risco": r[13],
                "risk": r[13],
                "resumo": r[14] or (r[6] or "")[:400],
                "synthesis": r[14],
                "eixo": r[15] or "",
                "model": r[16],
                "action_respond": r[17],
                "nivel": "indicio",
            }
        )

    pages = max(1, (int(total) + lim - 1) // lim)
    return {
        "status": "ok" if itens else "vazio",
        "nivel": "indicio",
        "total": int(total),
        "page": pg,
        "pages": pages,
        "limite": lim,
        "itens": itens,
    }


def mix_por_eixo(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    janela_horas: int = 168,
) -> dict[str, Any]:
    ensure_eixos(conn, campanha_id)
    eixos = list_eixos(conn, campanha_id)
    corte = datetime.now(timezone.utc) - timedelta(hours=max(1, janela_horas))
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(a.eixo), ''), 'outros') AS eixo, COUNT(*)::int
        FROM ctl.radar_item i
        LEFT JOIN ctl.radar_analise a ON a.item_id = i.id
        WHERE i.campanha_id = %s::uuid
          AND i.origem = 'oficial'
          AND i.published_at >= %s
        GROUP BY 1
        ORDER BY 2 DESC
        """,
        (campanha_id, corte),
    ).fetchall()
    counts = {r[0]: int(r[1]) for r in rows}
    total = sum(counts.values())
    dist = []
    for e in eixos:
        if not e["enabled"]:
            continue
        n = counts.get(e["name"], 0)
        dist.append(
            {
                "eixo": e["name"],
                "hint": e["hint"],
                "n": n,
                "pct": round(100.0 * n / total, 1) if total else 0.0,
            }
        )
    outros = counts.get("outros", 0)
    if outros:
        dist.append(
            {
                "eixo": "outros",
                "hint": "",
                "n": outros,
                "pct": round(100.0 * outros / total, 1) if total else 0.0,
            }
        )
    return {
        "status": "ok",
        "nivel": "indicio",
        "janela_horas": janela_horas,
        "total_oficial": total,
        "distribuicao": dist,
    }


def campanha_id_por_token(conn: psycopg.Connection, token: str) -> str | None:
    if not token:
        return None
    row = conn.execute(
        """
        SELECT campanha_id::text
        FROM ctl.mcp_token
        WHERE token = %s AND ativo IS TRUE
        """,
        (token,),
    ).fetchone()
    return row[0] if row and row[0] else None


def campanha_do_usuario(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT u.campanha_id::text, c.nome
        FROM ctl.apura_usuario u
        JOIN ctl.campanha c ON c.id = u.campanha_id
        WHERE u.id = %s::uuid AND u.ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def humanize_campanha_nome(slug: str) -> str:
    s = re.sub(r"[-_]+", " ", (slug or "").strip())
    return s.title() if s else "Campanha"
