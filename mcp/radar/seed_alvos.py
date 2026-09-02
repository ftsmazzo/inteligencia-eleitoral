"""Seed / sync de alvos a partir do nome da campanha e redes TSE."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import psycopg

from radar import store

# Mapeamento slug campanha → UF (para buscar redes TSE 2026)
_CAMPANHA_UF: dict[str, str] = {
    "governador-amapa": "AP",
    "alfredo-gaspar": "AL",
}


def _handle_from_url(url: str) -> tuple[str | None, str | None]:
    """Retorna (plataforma, handle) se reconhecível."""
    u = (url or "").strip()
    if not u:
        return None, None
    low = u.lower()
    try:
        path = urlparse(u if "://" in u else "https://" + u).path.strip("/")
    except Exception:
        path = ""
    parts = [p for p in path.split("/") if p]
    handle = parts[0] if parts else None
    if handle:
        handle = handle.lstrip("@").split("?")[0]
    if "instagram.com" in low:
        return "instagram", handle
    if "twitter.com" in low or "x.com" in low:
        return "x", handle
    if "facebook.com" in low or "fb.com" in low:
        return "facebook", handle
    return None, handle


def ensure_default_alvo(
    conn: psycopg.Connection,
    campanha_id: str,
    campanha_nome: str,
) -> dict[str, Any]:
    store.ensure_eixos(conn, campanha_id)
    alvos = store.list_alvos(conn, campanha_id, ativo_only=False)
    if alvos:
        return {"created": False, "alvos": len(alvos)}
    nome = store.humanize_campanha_nome(campanha_nome)
    store.upsert_alvo(
        conn,
        campanha_id,
        kind="pessoa",
        nome=nome,
        query_news=nome,
        is_own=True,
        ativo=True,
    )
    return {"created": True, "alvos": 1, "nome": nome}


def sync_tse_redes(
    conn: psycopg.Connection,
    campanha_id: str,
    campanha_nome: str,
    *,
    ano: int = 2026,
    limite: int = 30,
) -> dict[str, Any]:
    """Busca URLs Instagram no TSE ligadas ao nome da campanha / UF."""
    ensure_default_alvo(conn, campanha_id, campanha_nome)
    uf = _CAMPANHA_UF.get(campanha_nome.strip().lower())
    human = store.humanize_campanha_nome(campanha_nome)
    # tokens para ILIKE (Alfredo Gaspar → %Alfredo%Gaspar% / primeiro sobrenome)
    tokens = [t for t in re.split(r"\s+", human) if len(t) > 2]
    if not tokens:
        return {"added": 0, "matched": 0, "nota": "nome campanha curto"}

    like_nome = "%" + "%".join(tokens) + "%"
    params: list[Any] = [ano, like_nome, like_nome]
    uf_sql = ""
    if uf:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)
    params.append(max(1, min(limite, 50)))

    # eleicao.candidato + rede_social — tolerante se tabelas ausentes
    try:
        rows = conn.execute(
            f"""
            SELECT DISTINCT c.nm_urna, c.nm_candidato, r.ds_url, c.sg_uf
            FROM eleicao.rede_social r
            JOIN eleicao.candidato c
              ON c.ano = r.ano AND c.sq_candidato = r.sq_candidato
            WHERE r.ano = %s
              AND (c.nm_urna ILIKE %s OR c.nm_candidato ILIKE %s)
              {uf_sql}
              AND (
                lower(r.ds_url) LIKE '%%instagram.com%%'
                OR lower(r.ds_url) LIKE '%%twitter.com%%'
                OR lower(r.ds_url) LIKE '%%x.com%%'
              )
            ORDER BY c.nm_urna
            LIMIT %s
            """,
            params,
        ).fetchall()
    except Exception as e:
        return {"added": 0, "matched": 0, "erro": f"{type(e).__name__}: {e}"}

    existing = {
        ((a.get("handle_ig") or "").lower(), a["nome"].lower())
        for a in store.list_alvos(conn, campanha_id, ativo_only=False)
    }
    added = 0
    for nm_urna, nm_cand, url, sg_uf in rows:
        plat, handle = _handle_from_url(url or "")
        nome = (nm_urna or nm_cand or "").strip()
        if not nome:
            continue
        if plat == "instagram" and handle:
            key = (handle.lower(), nome.lower())
            if key in existing or (handle.lower(),) in {(h,) for h, _ in existing}:
                # atualiza handle no alvo próprio com mesmo nome
                continue
            is_own = all(t.lower() in nome.lower() for t in tokens[:2]) if tokens else False
            store.upsert_alvo(
                conn,
                campanha_id,
                kind="perfil",
                nome=nome,
                query_news=nome,
                handle_ig=handle,
                is_own=is_own,
                ativo=True,
            )
            existing.add((handle.lower(), nome.lower()))
            added += 1
        elif plat in ("x", "facebook") and nome:
            # tema/pessoa sem IG — garante query_news
            if any(a["nome"].lower() == nome.lower() for a in store.list_alvos(conn, campanha_id, ativo_only=False)):
                continue
            store.upsert_alvo(
                conn,
                campanha_id,
                kind="pessoa",
                nome=nome,
                query_news=nome,
                is_own=False,
                ativo=True,
            )
            added += 1

    return {
        "added": added,
        "matched": len(rows),
        "uf": uf,
        "ano": ano,
        "query": like_nome,
    }
