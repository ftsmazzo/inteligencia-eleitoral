"""Seed / sync de alvos — templates PULSO + tentativa TSE (pode estar vazio em 2026)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import psycopg

from radar import store

_CAMPANHA_UF: dict[str, str] = {
    "governador-amapa": "AP",
    "alfredo-gaspar": "AL",
}


def _handle_from_url(url: str) -> tuple[str | None, str | None]:
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
    return store.seed_template(conn, campanha_id, campanha_nome)


def sync_tse_redes(
    conn: psycopg.Connection,
    campanha_id: str,
    campanha_nome: str,
    *,
    ano: int = 2026,
    limite: int = 30,
) -> dict[str, Any]:
    """Tenta redes TSE; 2026 pode estar vazio. Também sincroniza por UF da config."""
    seed = ensure_default_alvo(conn, campanha_id, campanha_nome)
    cfg = store.get_config(conn, campanha_id)
    uf = (cfg.get("uf") or _CAMPANHA_UF.get(campanha_nome.strip().lower()) or "").upper() or None
    cand = (cfg.get("candidato_nome") or "").strip()
    tokens = [t for t in re.split(r"\s+", cand) if len(t) > 2]
    if not tokens:
        return {
            "added": 0,
            "matched": 0,
            "seed": seed,
            "nota": (
                "Sem nome de candidato na config. Preencha Configuração e/ou cadastre "
                "Instagram oficial (@) manualmente. Redes TSE 2026 podem estar vazias na base."
            ),
        }

    like_nome = "%" + "%".join(tokens) + "%"
    params: list[Any] = [ano, like_nome, like_nome]
    uf_sql = ""
    if uf:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)
    params.append(max(1, min(limite, 50)))

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
              AND lower(r.ds_url) LIKE '%%instagram.com%%'
            ORDER BY c.nm_urna
            LIMIT %s
            """,
            params,
        ).fetchall()
    except Exception as e:
        return {
            "added": 0,
            "matched": 0,
            "seed": seed,
            "erro": f"{type(e).__name__}: {e}",
            "nota": "Falha ao consultar eleicao.rede_social. Use Alvos manuais.",
        }

    if not rows:
        return {
            "added": 0,
            "matched": 0,
            "seed": seed,
            "uf": uf,
            "ano": ano,
            "query": like_nome,
            "nota": (
                f"Nenhuma rede Instagram no TSE para ano={ano} / {like_nome}. "
                "Pacote br_cand_rede_social 2026 pode não estar carregado. "
                "Cadastre o @ oficial em Alvos → Instagram oficial."
            ),
        }

    existing_handles = {
        (a.get("handle_ig") or "").lower()
        for a in store.list_alvos(conn, campanha_id, ativo_only=False)
        if a.get("handle_ig")
    }
    added = 0
    for nm_urna, nm_cand, url, _sg in rows:
        plat, handle = _handle_from_url(url or "")
        if plat != "instagram" or not handle:
            continue
        if handle.lower() in existing_handles:
            continue
        nome = (nm_urna or nm_cand or handle).strip()
        is_own = all(t.lower() in nome.lower() for t in tokens[:2]) if len(tokens) >= 1 else False
        store.upsert_alvo(
            conn,
            campanha_id,
            kind="perfil",
            nome=nome,
            query_news=nome,
            handle_ig=handle,
            is_own=is_own,
            papel="proprio" if is_own else "aliado",
            prioridade=1 if is_own else 4,
            ativo=True,
        )
        existing_handles.add(handle.lower())
        added += 1

    return {
        "added": added,
        "matched": len(rows),
        "seed": seed,
        "uf": uf,
        "ano": ano,
        "query": like_nome,
        "nota": f"Importados {added} handles Instagram do TSE." if added else "Já estavam cadastrados.",
    }
