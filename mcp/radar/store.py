"""CRUD store do Radar (filtrado por campanha_id uuid) — alinhado PULSO + main.py."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

BRT = ZoneInfo("America/Sao_Paulo")
KINDS = ("pessoa", "adversario", "tema", "perfil")

# (nome, dica/explicação para a IA, palavras-chave)
DEFAULT_EIXOS = [
    (
        "Gestao e entregas",
        "Resultados de governo, obras e serviços públicos prestados à população",
        "obras, servicos, saude, educacao, resultado de governo",
    ),
    (
        "Territorio e interior",
        "Presença territorial, visitas e vínculo com municípios e bairros",
        "cidade, municipio, visita, interior, bairro",
    ),
    (
        "Enfrentamento",
        "Contraste com adversários, denúncias e resposta a ataques",
        "adversario, denuncia, contraste, resposta a ataque",
    ),
    (
        "Identidade",
        "Trajetória, valores, biografia, fé e família do candidato",
        "trajetoria, valores, biografia, fe, familia",
    ),
    (
        "Mobilizacao",
        "Pedido de voto, afiliação, adesão e eventos de campanha",
        "voto, urna, afiliacao, adesao, evento de campanha",
    ),
]

# Config mínima por slug (só nome/UF/cargo). Alvos vêm do seed Gestão, não de placeholder.
_SEED_TEMPLATES: dict[str, dict[str, Any]] = {
    "governador-amapa": {
        "candidato_nome": "CLÉCIO",
        "uf": "AP",
        "cargo": "governador",
        "alvos": [],
    },
    "alfredo-gaspar": {
        "candidato_nome": "Alfredo Gaspar",
        "uf": "AL",
        "cargo": "deputado federal",
        "alvos": [],
    },
}


def fingerprint(campanha_id: str, url: str | None, titulo: str) -> str:
    raw = f"{campanha_id}|{url or ''}|{titulo or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fmt_brt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime("%d/%m %H:%M")


def humanize_campanha_nome(slug: str) -> str:
    s = re.sub(r"[-_]+", " ", (slug or "").strip())
    return s.title() if s else "Campanha"


def ensure_eixos(conn: psycopg.Connection, campanha_id: str) -> None:
    """Insere eixos padrão se faltarem (por nome). Não recria eixos apagados com outro nome."""
    from radar.schema import ensure_keywords_column

    has_kw = ensure_keywords_column(conn)
    for name, hint, keywords in DEFAULT_EIXOS:
        if has_kw:
            conn.execute(
                """
                INSERT INTO ctl.radar_eixo (campanha_id, name, hint, keywords, enabled)
                VALUES (%s::uuid, %s, %s, %s, TRUE)
                ON CONFLICT (campanha_id, name) DO NOTHING
                """,
                (campanha_id, name, hint, keywords),
            )
        else:
            conn.execute(
                """
                INSERT INTO ctl.radar_eixo (campanha_id, name, hint, enabled)
                VALUES (%s::uuid, %s, %s, TRUE)
                ON CONFLICT (campanha_id, name) DO NOTHING
                """,
                (campanha_id, name, hint),
            )
    if not has_kw:
        return
    for name, _hint, keywords in DEFAULT_EIXOS:
        conn.execute(
            """
            UPDATE ctl.radar_eixo
            SET keywords = %s
            WHERE campanha_id = %s::uuid AND name = %s
              AND COALESCE(TRIM(keywords), '') = ''
            """,
            (keywords, campanha_id, name),
        )
    for name, hint, keywords in DEFAULT_EIXOS:
        conn.execute(
            """
            UPDATE ctl.radar_eixo
            SET hint = %s
            WHERE campanha_id = %s::uuid AND name = %s
              AND TRIM(hint) = TRIM(%s)
            """,
            (hint, campanha_id, name, keywords),
        )


def list_eixos(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    seed_if_empty: bool = False,
) -> list[dict[str, Any]]:
    from radar.schema import ensure_keywords_column

    has_kw = ensure_keywords_column(conn)
    if seed_if_empty:
        n = conn.execute(
            "SELECT count(*) FROM ctl.radar_eixo WHERE campanha_id = %s::uuid",
            (campanha_id,),
        ).fetchone()
        if not n or int(n[0] or 0) == 0:
            ensure_eixos(conn, campanha_id)
    if has_kw:
        rows = conn.execute(
            """
            SELECT id::text, name, hint, COALESCE(keywords, ''), enabled
            FROM ctl.radar_eixo
            WHERE campanha_id = %s::uuid
            ORDER BY name
            """,
            (campanha_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id::text, name, hint, '', enabled
            FROM ctl.radar_eixo
            WHERE campanha_id = %s::uuid
            ORDER BY name
            """,
            (campanha_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "hint": r[2] or "",
            "keywords": r[3] or "",
            "enabled": bool(r[4]),
        }
        for r in rows
    ]


def upsert_eixo(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    name: str,
    hint: str = "",
    keywords: str = "",
    enabled: bool = True,
    eixo_id: str | None = None,
) -> dict[str, Any]:
    from radar.schema import ensure_keywords_column

    has_kw = ensure_keywords_column(conn)
    name = (name or "").strip()
    if not name:
        raise ValueError("nome do eixo obrigatorio")
    hint = (hint or "").strip()
    keywords = (keywords or "").strip()
    if eixo_id:
        if has_kw:
            row = conn.execute(
                """
                UPDATE ctl.radar_eixo
                SET name=%s, hint=%s, keywords=%s, enabled=%s
                WHERE id=%s::uuid AND campanha_id=%s::uuid
                RETURNING id::text, name, hint, COALESCE(keywords, ''), enabled
                """,
                (name, hint, keywords, enabled, eixo_id, campanha_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE ctl.radar_eixo
                SET name=%s, hint=%s, enabled=%s
                WHERE id=%s::uuid AND campanha_id=%s::uuid
                RETURNING id::text, name, hint, '', enabled
                """,
                (name, hint, enabled, eixo_id, campanha_id),
            ).fetchone()
        if not row:
            raise ValueError("eixo nao encontrado")
    else:
        if has_kw:
            row = conn.execute(
                """
                INSERT INTO ctl.radar_eixo (campanha_id, name, hint, keywords, enabled)
                VALUES (%s::uuid, %s, %s, %s, %s)
                ON CONFLICT (campanha_id, name) DO UPDATE SET
                  hint = EXCLUDED.hint,
                  keywords = EXCLUDED.keywords,
                  enabled = EXCLUDED.enabled
                RETURNING id::text, name, hint, COALESCE(keywords, ''), enabled
                """,
                (campanha_id, name, hint, keywords, enabled),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO ctl.radar_eixo (campanha_id, name, hint, enabled)
                VALUES (%s::uuid, %s, %s, %s)
                ON CONFLICT (campanha_id, name) DO UPDATE SET
                  hint = EXCLUDED.hint,
                  enabled = EXCLUDED.enabled
                RETURNING id::text, name, hint, '', enabled
                """,
                (campanha_id, name, hint, enabled),
            ).fetchone()
    return {
        "id": row[0],
        "name": row[1],
        "hint": row[2] or "",
        "keywords": (row[3] or "") if has_kw else keywords,
        "enabled": bool(row[4]),
    }


def delete_eixo(conn: psycopg.Connection, campanha_id: str, eixo_id: str) -> None:
    conn.execute(
        "DELETE FROM ctl.radar_eixo WHERE id=%s::uuid AND campanha_id=%s::uuid",
        (eixo_id, campanha_id),
    )


def merge_eixo_keywords(
    conn: psycopg.Connection,
    campanha_id: str,
    keywords_por_eixo: dict[str, str],
) -> int:
    """Mescla keywords extraídas sem apagar as existentes."""
    from radar.schema import ensure_keywords_column

    if not ensure_keywords_column(conn):
        return 0
    updated = 0
    for name, kws in (keywords_por_eixo or {}).items():
        extra = [x.strip() for x in (kws or "").split(",") if x.strip()]
        if not extra:
            continue
        row = conn.execute(
            """
            SELECT id::text, COALESCE(keywords, '')
            FROM ctl.radar_eixo
            WHERE campanha_id=%s::uuid AND name=%s
            """,
            (campanha_id, name),
        ).fetchone()
        if not row:
            continue
        cur = [x.strip() for x in (row[1] or "").split(",") if x.strip()]
        seen = {c.lower() for c in cur}
        for e in extra:
            if e.lower() not in seen:
                cur.append(e)
                seen.add(e.lower())
        conn.execute(
            "UPDATE ctl.radar_eixo SET keywords=%s WHERE id=%s::uuid",
            (", ".join(cur), row[0]),
        )
        updated += 1
    return updated


def get_config(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT candidato_nome, uf, cargo, notas, atualizado_em
        FROM ctl.radar_config WHERE campanha_id = %s::uuid
        """,
        (campanha_id,),
    ).fetchone()
    if not row:
        return {
            "candidato_nome": "",
            "uf": None,
            "cargo": None,
            "notas": "",
            "atualizado_em": None,
        }
    return {
        "candidato_nome": row[0] or "",
        "uf": row[1],
        "cargo": row[2],
        "notas": row[3] or "",
        "atualizado_em": row[4].isoformat() if row[4] else None,
    }


def upsert_config(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    candidato_nome: str = "",
    uf: str | None = None,
    cargo: str | None = None,
    notas: str = "",
) -> dict[str, Any]:
    uf_n = (uf or "").strip().upper()[:2] or None
    conn.execute(
        """
        INSERT INTO ctl.radar_config (campanha_id, candidato_nome, uf, cargo, notas, atualizado_em)
        VALUES (%s::uuid, %s, %s, %s, %s, now())
        ON CONFLICT (campanha_id) DO UPDATE SET
          candidato_nome = EXCLUDED.candidato_nome,
          uf = EXCLUDED.uf,
          cargo = EXCLUDED.cargo,
          notas = EXCLUDED.notas,
          atualizado_em = now()
        """,
        (campanha_id, (candidato_nome or "").strip(), uf_n, (cargo or "").strip() or None, notas or ""),
    )
    return get_config(conn, campanha_id)


def list_alvos(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    ativo_only: bool = True,
) -> list[dict[str, Any]]:
    q = """
        SELECT id::text, kind, nome, query_news, handle_ig, is_own, ativo,
               last_seen_at, criado_em,
               COALESCE(papel, ''), COALESCE(notas, ''), COALESCE(prioridade, 5)
        FROM ctl.radar_alvo
        WHERE campanha_id = %s::uuid
    """
    if ativo_only:
        q += " AND ativo IS TRUE"
    q += " ORDER BY prioridade ASC, is_own DESC, kind, nome"
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
            "papel": r[9] or "",
            "notas": r[10] or "",
            "prioridade": int(r[11] or 5),
            "mix": bool(r[5]) and r[1] == "perfil",
        }
        for r in rows
    ]


def alvos_agrupados(conn: psycopg.Connection, campanha_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = list_alvos(conn, campanha_id, ativo_only=False)
    out: dict[str, list[dict[str, Any]]] = {
        "pessoas": [],
        "adversarios": [],
        "temas": [],
        "instagram_oficial": [],
        "instagram_outros": [],
    }
    for a in rows:
        if a["kind"] == "adversario":
            out["adversarios"].append(a)
        elif a["kind"] == "tema":
            out["temas"].append(a)
        elif a["kind"] == "perfil":
            if a["is_own"]:
                out["instagram_oficial"].append(a)
            else:
                out["instagram_outros"].append(a)
        else:
            out["pessoas"].append(a)
    return out


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
    papel: str | None = None,
    notas: str = "",
    prioridade: int = 5,
    alvo_id: str | None = None,
) -> dict[str, Any]:
    kind = (kind or "pessoa").strip().lower()
    if kind not in KINDS:
        raise ValueError("kind invalido (pessoa|adversario|tema|perfil)")
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("nome obrigatorio")
    handle = (handle_ig or "").strip().lstrip("@") or None
    if kind == "perfil" and not handle and not alvo_id:
        # permite placeholder "preencher @"
        pass
    if kind != "perfil":
        is_own = False
        handle = handle  # IG opcional em pessoa/adversario também (atalho)
    # papel default
    if not papel:
        papel = {
            "pessoa": "proprio",
            "adversario": "adversario",
            "tema": "tema",
            "perfil": "proprio" if is_own else "aliado",
        }.get(kind, "")
    qn = (query_news or (nome if kind != "perfil" else "")).strip()
    pri = max(1, min(10, int(prioridade or 5)))
    if alvo_id:
        conn.execute(
            """
            UPDATE ctl.radar_alvo
            SET kind=%s, nome=%s, query_news=%s, handle_ig=%s, is_own=%s, ativo=%s,
                papel=%s, notas=%s, prioridade=%s
            WHERE id=%s::uuid AND campanha_id=%s::uuid
            """,
            (kind, nome, qn, handle, is_own, ativo, papel, notas or "", pri, alvo_id, campanha_id),
        )
        aid = alvo_id
    else:
        row = conn.execute(
            """
            INSERT INTO ctl.radar_alvo (
              campanha_id, kind, nome, query_news, handle_ig, is_own, ativo,
              papel, notas, prioridade
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text
            """,
            (campanha_id, kind, nome, qn, handle, is_own, ativo, papel, notas or "", pri),
        ).fetchone()
        aid = row[0]
    rows = list_alvos(conn, campanha_id, ativo_only=False)
    return next(a for a in rows if a["id"] == aid)


def _normalizar_txt(s: str | None) -> str:
    import unicodedata

    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def chave_alvo(kind: str, nome: str | None, handle_ig: str | None = None) -> str:
    """Identidade estável do alvo p/ lista de bloqueio — sobrevive a recriação com outro id."""
    if kind == "perfil" and handle_ig:
        return f"ig:{_normalizar_txt(handle_ig).lstrip('@')}"
    return f"{(kind or 'alvo').strip().lower()}:nome:{_normalizar_txt(nome)}"


def marcar_excluido(conn: psycopg.Connection, campanha_id: str, kind: str, nome: str | None, handle_ig: str | None = None) -> None:
    """Registra que este alvo foi apagado manualmente — seed/coleta nunca mais recria."""
    from radar.schema import ensure_excluido_table

    if not ensure_excluido_table(conn):
        return
    chave = chave_alvo(kind, nome, handle_ig)
    try:
        conn.execute(
            """
            INSERT INTO ctl.radar_alvo_excluido (campanha_id, chave)
            VALUES (%s::uuid, %s)
            ON CONFLICT (campanha_id, chave) DO NOTHING
            """,
            (campanha_id, chave),
        )
    except Exception:
        pass


def esta_excluido(conn: psycopg.Connection, campanha_id: str, kind: str, nome: str | None, handle_ig: str | None = None) -> bool:
    from radar.schema import ensure_excluido_table

    if not ensure_excluido_table(conn):
        return False
    chave = chave_alvo(kind, nome, handle_ig)
    try:
        row = conn.execute(
            "SELECT 1 FROM ctl.radar_alvo_excluido WHERE campanha_id=%s::uuid AND chave=%s",
            (campanha_id, chave),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def list_excluidos(conn: psycopg.Connection, campanha_id: str) -> list[str]:
    from radar.schema import ensure_excluido_table

    if not ensure_excluido_table(conn):
        return []
    try:
        rows = conn.execute(
            "SELECT chave FROM ctl.radar_alvo_excluido WHERE campanha_id=%s::uuid ORDER BY criado_em DESC",
            (campanha_id,),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def desbloquear(conn: psycopg.Connection, campanha_id: str, chave: str) -> None:
    """Remove da lista de bloqueio — seed volta a poder recriar esse alvo."""
    from radar.schema import ensure_excluido_table

    if not ensure_excluido_table(conn):
        return
    conn.execute(
        "DELETE FROM ctl.radar_alvo_excluido WHERE campanha_id=%s::uuid AND chave=%s",
        (campanha_id, chave),
    )


def delete_alvo(conn: psycopg.Connection, campanha_id: str, alvo_id: str) -> None:
    row = conn.execute(
        "SELECT kind, nome, handle_ig FROM ctl.radar_alvo WHERE id=%s::uuid AND campanha_id=%s::uuid",
        (alvo_id, campanha_id),
    ).fetchone()
    conn.execute(
        "DELETE FROM ctl.radar_alvo WHERE id=%s::uuid AND campanha_id=%s::uuid",
        (alvo_id, campanha_id),
    )
    if row:
        # Lembra a exclusão p/ "Preencher da Gestão" nunca mais recriar este alvo.
        marcar_excluido(conn, campanha_id, row[0], row[1], row[2])


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
    entity_kind: str | None = None,
) -> str | None:
    pub = published_at or datetime.now(timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    fp = fingerprint(campanha_id, url, titulo)
    row = conn.execute(
        """
        INSERT INTO ctl.radar_item (
          campanha_id, origem, canal, fonte, url, titulo, body,
          published_at, fingerprint, entity_name, entity_kind
        )
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            entity_kind,
        ),
    ).fetchone()
    return row[0] if row else None


def save_analise(conn: psycopg.Connection, item_id: str, data: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO ctl.radar_analise (
          item_id, tipo, urgencia, polarity, score, risk, synthesis,
          eixo, model, action_respond, action_ignore, action_monitor
        )
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (item_id) DO UPDATE SET
          tipo=EXCLUDED.tipo,
          urgencia=EXCLUDED.urgencia,
          polarity=EXCLUDED.polarity,
          score=EXCLUDED.score,
          risk=EXCLUDED.risk,
          synthesis=EXCLUDED.synthesis,
          eixo=EXCLUDED.eixo,
          model=EXCLUDED.model,
          action_respond=EXCLUDED.action_respond,
          action_ignore=EXCLUDED.action_ignore,
          action_monitor=EXCLUDED.action_monitor
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
            data.get("action_ignore"),
            data.get("action_monitor"),
        ),
    )


def start_run(conn: psycopg.Connection, campanha_id: str | None, mode: str) -> str:
    row = conn.execute(
        """
        INSERT INTO ctl.radar_run (campanha_id, mode, ok)
        VALUES (%s::uuid, %s, 0)
        RETURNING id::text
        """,
        (campanha_id, mode),
    ).fetchone()
    return row[0]


def finish_run(conn: psycopg.Connection, run_id: str, *, ok: int, err: str | None = None) -> None:
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
          COUNT(*) FILTER (WHERE i.origem = 'oficial')::int,
          COUNT(*) FILTER (WHERE lower(COALESCE(a.urgencia,'')) IN ('alta','critica'))::int
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
               COUNT(*) FILTER (WHERE kind = 'perfil' AND is_own)::int,
               COUNT(*) FILTER (WHERE kind = 'adversario')::int
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
        "alertas_24h": int(row[4] or 0),
        "alvos": int(alvos[0] or 0),
        "ig_oficial": int(alvos[1] or 0),
        "adversarios": int(alvos[2] or 0),
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
    entity_kind: str | None = None,
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
    if entity_kind:
        where.append("lower(COALESCE(i.entity_kind, '')) = %s")
        params.append(entity_kind.strip().lower())
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
               i.published_at, i.entity_name, i.entity_kind,
               a.tipo, a.urgencia, a.polarity, a.score, a.risk, a.synthesis,
               a.eixo, a.model, a.action_respond, a.action_monitor
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
                "entity_kind": r[9],
                "tipo": r[10],
                "urgencia": r[11],
                "tom": r[12],
                "polarity": r[12],
                "clima_score": r[13],
                "score": r[13],
                "risco": r[14],
                "risk": r[14],
                "resumo": r[15] or (r[6] or "")[:400],
                "synthesis": r[15],
                "eixo": r[16] or "",
                "model": r[17],
                "action_respond": r[18],
                "action_monitor": r[19],
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


def alertas(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    janela_horas: int = 48,
    limite: int = 30,
) -> dict[str, Any]:
    data = stream(
        conn,
        campanha_id,
        origem="clima",
        janela_horas=janela_horas,
        page=1,
        limite=100,
    )
    urg = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    itens = [
        it
        for it in data.get("itens") or []
        if (it.get("urgencia") or "").lower() in ("alta", "critica")
        or (isinstance(it.get("score"), int) and it["score"] <= -40)
        or (it.get("tipo") or "").lower() in ("ataque", "escandalo", "escândalo")
    ]
    itens.sort(key=lambda x: (urg.get((x.get("urgencia") or "").lower(), 9), x.get("score") or 0))
    itens = itens[: max(1, min(limite, 50))]
    return {
        "status": "ok" if itens else "vazio",
        "nivel": "indicio",
        "janela_horas": janela_horas,
        "total": len(itens),
        "itens": itens,
        "nota": "Alertas = urgência alta/crítica, ataque/escândalo ou score ≤ -40. Revisão humana obrigatória.",
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
    # desvios simples
    ideal = 100.0 / max(1, len([d for d in dist if d["eixo"] != "outros"]))
    for d in dist:
        if d["eixo"] == "outros":
            d["desvio"] = None
            continue
        d["desvio"] = round(d["pct"] - ideal, 1)
        d["status"] = (
            "super" if d["desvio"] >= 8 else ("sub" if d["desvio"] <= -8 else "ok")
        )
    ig = [
        a
        for a in list_alvos(conn, campanha_id, ativo_only=True)
        if a["kind"] == "perfil" and a["is_own"]
    ]
    return {
        "status": "ok",
        "nivel": "indicio",
        "janela_horas": janela_horas,
        "total_oficial": total,
        "distribuicao": dist,
        "instagram_oficial": ig,
        "nota": "Termômetro PULSO: só peças origem=oficial (IG marcado is_own).",
    }


def sintese_semanal(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    """Rascunho RELATÓRIO PULSO a partir do store — revisão humana.

    Evita texto genérico: usa nomes reais dos alvos, contagens e scores desta
    campanha (não frases prontas) sempre que o dado existir no store.
    """
    cfg = get_config(conn, campanha_id)
    kpi = kpi_24h(conn, campanha_id)
    alerta = alertas(conn, campanha_id, janela_horas=168, limite=10)
    mix = mix_por_eixo(conn, campanha_id, janela_horas=168)
    clima = stream(conn, campanha_id, origem="clima", janela_horas=168, page=1, limite=40)
    ativos = [a for a in list_alvos(conn, campanha_id, ativo_only=True)]
    n_adv = len([a for a in ativos if a["kind"] == "adversario"])
    n_temas = len([a for a in ativos if a["kind"] == "tema"])
    ig_oficial = [a for a in ativos if a["kind"] == "perfil" and a["is_own"]]

    itens_clima = clima.get("itens") or []
    itens_proprio = [it for it in itens_clima if (it.get("entity_kind") or "") != "adversario"]
    itens_adv = [it for it in itens_clima if (it.get("entity_kind") or "") == "adversario"]

    def _agrupar_por_alvo(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agrup: dict[str, dict[str, Any]] = {}
        for it in itens:
            nome_alvo = it.get("alvo") or it.get("entity_name") or "—"
            g = agrup.setdefault(nome_alvo, {"alvo": nome_alvo, "n": 0, "scores": [], "exemplo": it})
            g["n"] += 1
            if isinstance(it.get("score"), (int, float)):
                g["scores"].append(it["score"])
        out = []
        for g in agrup.values():
            score_medio = round(sum(g["scores"]) / len(g["scores"]), 1) if g["scores"] else None
            ex = g["exemplo"]
            out.append(
                {
                    "alvo": g["alvo"],
                    "menções": g["n"],
                    "score_medio": score_medio,
                    "titulo_recente": ex.get("titulo"),
                    "quando": ex.get("quando"),
                    "urgencia": ex.get("urgencia"),
                    "fonte": ex.get("fonte"),
                }
            )
        out.sort(key=lambda x: -x["menções"])
        return out

    resumo = (
        f"{cfg.get('candidato_nome') or 'Candidato'} · {cfg.get('cargo') or ''} {cfg.get('uf') or ''} · "
        f"{kpi.get('itens_24h', 0)} itens nas últimas 24h ({kpi.get('clima_24h', 0)} clima / "
        f"{kpi.get('oficial_24h', 0)} oficial) · {kpi.get('alertas_24h', 0)} alerta(s) alta/crítica · "
        f"{n_adv} adversário(s) monitorado(s) · {n_temas} tema(s) do plano de governo · "
        f"{len(ig_oficial)} perfil(is) oficial(is) no Mix"
    ).strip()

    return {
        "status": "ok",
        "nivel": "indicio",
        "candidato": cfg.get("candidato_nome") or "",
        "uf": cfg.get("uf"),
        "resumo": resumo,
        "blocos": {
            "cenario": _agrupar_por_alvo(itens_proprio)[:6],
            "comunicacao": mix.get("distribuicao") or [],
            "adversarios": _agrupar_por_alvo(itens_adv)[:6],
            "alertas": [
                {
                    "titulo": it["titulo"],
                    "alvo": it.get("alvo") or it.get("entity_name"),
                    "urgencia": it.get("urgencia"),
                    "tipo": it.get("tipo"),
                    "score": it.get("score"),
                    "quando": it.get("quando"),
                }
                for it in (alerta.get("itens") or [])[:6]
            ],
            "recomendacoes": _recomendacoes(cfg, kpi, mix, ig_oficial, n_adv, alerta),
        },
        "nota": "Rascunho automático PULSO — nomes, contagens e scores vêm do que foi coletado desta campanha. Não é entrega final — revisão humana obrigatória.",
    }


def _recomendacoes(
    cfg: dict[str, Any],
    kpi: dict[str, Any],
    mix: dict[str, Any],
    ig_oficial: list[dict[str, Any]],
    n_adv: int,
    alerta: dict[str, Any],
) -> list[str]:
    """Recomendações específicas desta campanha — não frases genéricas fixas."""
    out: list[str] = []
    n_alertas = int(kpi.get("alertas_24h") or 0)
    if n_alertas:
        titulos = ", ".join(it["titulo"] for it in (alerta.get("itens") or [])[:2])
        out.append(f"{n_alertas} alerta(s) alta/crítica nas 24h — revisar primeiro: {titulos}.")
    for d in mix.get("distribuicao") or []:
        if d.get("status") == "super":
            out.append(f"Eixo '{d['eixo']}' super-representado ({d['pct']}% das peças oficiais) — variar comunicação.")
        elif d.get("status") == "sub":
            out.append(f"Eixo '{d['eixo']}' sub-representado ({d['pct']}%) — {d.get('hint') or 'pouca peça nesse eixo'}.")
    if not ig_oficial:
        out.append("Nenhum Instagram oficial cadastrado — Mix fica sem dado; cadastre o @ do candidato em Alvos.")
    if not n_adv:
        out.append("Nenhum adversário cadastrado em Alvos — sem contraste no clima. Cadastre concorrentes do mesmo pleito.")
    if not out:
        out.append(f"Sem pendência crítica nesta janela para {cfg.get('candidato_nome') or 'a campanha'} — manter monitoramento.")
    return out[:6]


def campanha_do_usuario(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str] | None:
    """Campanha de trabalho: campanha_ativa_id (seletor), senão legado campanha_id."""
    row = conn.execute(
        """
        SELECT COALESCE(u.campanha_ativa_id, u.campanha_id)::text, c.nome
        FROM ctl.apura_usuario u
        JOIN ctl.campanha c ON c.id = COALESCE(u.campanha_ativa_id, u.campanha_id)
        WHERE u.id = %s::uuid AND u.ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def seed_template(conn: psycopg.Connection, campanha_id: str, campanha_nome: str) -> dict[str, Any]:
    """Garante config + eixos. NÃO cria alvos automaticamente (evita reidratar após apagar).

    Alvos vêm só de POST /gestao/seed-radar ou cadastro manual.
    """
    ensure_eixos(conn, campanha_id)
    slug = (campanha_nome or "").strip().lower()
    tpl = _SEED_TEMPLATES.get(slug)
    cfg = get_config(conn, campanha_id)
    if tpl and not (cfg.get("candidato_nome") or "").strip():
        upsert_config(
            conn,
            campanha_id,
            candidato_nome=tpl["candidato_nome"],
            uf=tpl.get("uf"),
            cargo=tpl.get("cargo"),
        )
        cfg = get_config(conn, campanha_id)
    elif not (cfg.get("candidato_nome") or "").strip():
        upsert_config(
            conn,
            campanha_id,
            candidato_nome=humanize_campanha_nome(campanha_nome),
        )
        cfg = get_config(conn, campanha_id)

    existing = list_alvos(conn, campanha_id, ativo_only=False)
    return {"created": False, "alvos": len(existing), "config": cfg}


def resetar_radar(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    """Apaga stream, alvos e runs da campanha. Mantém eixos. Config permanece (nome/UF)."""
    n_itens = conn.execute(
        "DELETE FROM ctl.radar_item WHERE campanha_id = %s::uuid",
        (campanha_id,),
    ).rowcount
    n_alvos = conn.execute(
        "DELETE FROM ctl.radar_alvo WHERE campanha_id = %s::uuid",
        (campanha_id,),
    ).rowcount
    try:
        n_runs = conn.execute(
            "DELETE FROM ctl.radar_run WHERE campanha_id = %s::uuid",
            (campanha_id,),
        ).rowcount
    except Exception:
        n_runs = 0
    return {
        "ok": True,
        "itens_apagados": int(n_itens or 0),
        "alvos_apagados": int(n_alvos or 0),
        "runs_apagados": int(n_runs or 0),
        "config": get_config(conn, campanha_id),
    }
