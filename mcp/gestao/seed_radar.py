"""Seed Radar a partir do escopo Gestão + memória + planos (sq exato). Aditivo — nunca apaga."""
from __future__ import annotations

from typing import Any

import psycopg

from gestao import memoria
from gestao import temas_plano
from gestao.store import get_status
from radar import store as radar_store

_IG_LIXO = {
    "channel",
    "share",
    "instagram",
    "www",
    "p",
    "reel",
    "reels",
    "tv",
    "stories",
    "explore",
    "accounts",
    "direct",
    "about",
}


def _ig_ok(h: str | None) -> str | None:
    if not h:
        return None
    clean = h.strip().lstrip("@").split("?")[0].strip()
    if not clean or clean.lower() in _IG_LIXO:
        return None
    if len(clean) < 2 or "/" in clean or " " in clean:
        return None
    return clean


def _igs_limpos(raw: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for h in raw or []:
        ok = _ig_ok(str(h) if h else None)
        if not ok:
            continue
        key = ok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ok)
    return out


def _existe(
    existentes: list[dict[str, Any]],
    *,
    nome: str | None = None,
    handle: str | None = None,
) -> bool:
    if handle:
        h = handle.lower().lstrip("@")
        if any((a.get("handle_ig") or "").lower() == h for a in existentes):
            return True
    if nome:
        nl = nome.strip().lower()
        if any((a.get("nome") or "").strip().lower() == nl for a in existentes):
            return True
    return False


def seed_radar_da_gestao(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    """Preenche Alvos a partir da Gestão. Sempre ADITIVO — nunca apaga o que já existe
    (inclusive alvos cadastrados à mão, como Instagram oficial validado manualmente)."""
    st = get_status(conn, campanha_id)
    if not st.get("nm_urna") and not st.get("nm_candidato"):
        raise ValueError("Escopo sem candidato")

    nome = st.get("nm_urna") or st.get("nm_candidato")
    uf = st.get("sg_uf")
    cargo = st.get("cargo_label") or ""
    partido = st.get("sg_partido")
    sq = st.get("sq_candidato")

    try:
        conn.execute(
            """
            INSERT INTO ctl.radar_config (campanha_id, candidato_nome, uf, cargo, atualizado_em)
            VALUES (%s::uuid, %s, %s, %s, now())
            ON CONFLICT (campanha_id) DO UPDATE SET
              candidato_nome = EXCLUDED.candidato_nome,
              uf = EXCLUDED.uf,
              cargo = EXCLUDED.cargo,
              atualizado_em = now()
            """,
            (campanha_id, nome, uf, cargo),
        )
    except Exception:
        pass

    radar_store.ensure_eixos(conn, campanha_id)
    added = 0
    stats = {"pessoa": 0, "adversario": 0, "perfil": 0, "tema": 0, "eixos_kw": 0}

    existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
    if not _existe(existentes, nome=nome):
        radar_store.upsert_alvo(
            conn,
            campanha_id,
            kind="pessoa",
            nome=nome,
            query_news=f"{nome} {uf or ''} {cargo}".strip(),
            handle_ig=None,
            is_own=False,
            papel="proprio",
            prioridade=1,
            notas=f"{partido or ''} · monitorado (candidato do escopo)".strip(" ·"),
        )
        added += 1
        stats["pessoa"] += 1

    pessoas: list[dict[str, Any]] = []
    blocos = memoria.listar(conn, campanha_id, tipo="base_redes", limite=3)
    for b in blocos:
        meta = b.get("meta") or {}
        pessoas.extend(meta.get("pessoas") or [])

    # adversários com sq_candidato (para casar plano de governo com precisão)
    adversarios_sq: list[dict[str, Any]] = []

    for p in pessoas:
        papel = p.get("papel") or "adversario"
        nm = (p.get("nm_urna") or "").strip()
        sq_p = p.get("sq_candidato")
        igs = _igs_limpos(p.get("ig"))
        proprio = papel == "proprio"

        if not proprio and nm and nm != nome:
            adversarios_sq.append({"nome": nm, "sq_candidato": sq_p})
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if not _existe(existentes, nome=nm):
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="adversario",
                    nome=nm,
                    query_news=f"{nm} {uf or ''}".strip(),
                    handle_ig=None,
                    is_own=False,
                    papel="adversario",
                    prioridade=2,
                    notas=(p.get("sg_partido") or ""),
                )
                added += 1
                stats["adversario"] += 1

        for h in igs:
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if _existe(existentes, handle=h):
                continue
            radar_store.upsert_alvo(
                conn,
                campanha_id,
                kind="perfil",
                nome=f"@{h}" + (" (oficial)" if proprio else f" ({nm})" if nm else ""),
                query_news="" if proprio else f"{nm} {uf or ''}".strip(),
                handle_ig=h,
                is_own=proprio,
                papel="proprio" if proprio else "adversario",
                prioridade=1 if proprio else 2,
            )
            added += 1
            stats["perfil"] += 1

    # fallback: adversários citados na nominata mesmo sem IG na base_redes
    if not adversarios_sq:
        conc = memoria.listar(conn, campanha_id, tipo="base_concorrentes", limite=1)
        if conc:
            linhas = [
                ln.strip()[2:]
                for ln in (conc[0].get("corpo") or "").splitlines()
                if ln.strip().startswith("- ")
            ]
            for ln in linhas[:8]:
                nome_adv = ln.split("·")[0].strip()
                if not nome_adv or nome_adv == nome:
                    continue
                adversarios_sq.append({"nome": nome_adv, "sq_candidato": None})
                existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
                if _existe(existentes, nome=nome_adv):
                    continue
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="adversario",
                    nome=nome_adv,
                    query_news=f"{nome_adv} {uf or ''}",
                    handle_ig=None,
                    is_own=False,
                    papel="adversario",
                    prioridade=2,
                )
                added += 1
                stats["adversario"] += 1

    # Temas + keywords a partir do plano de governo (só sq exato — sem cruzar nome).
    extracao: dict[str, Any] = {
        "temas_proprio": [],
        "temas_adversario": [],
        "keywords_eixos": {},
        "plano_chars": 0,
    }
    try:
        extracao = temas_plano.extrair_campanha(
            conn,
            campanha_id=campanha_id,
            uf=uf,
            sq_candidato=str(sq) if sq else None,
            nm_candidato=nome,
            adversarios=adversarios_sq,
        )
    except Exception:
        pass
    try:
        stats["eixos_kw"] = radar_store.merge_eixo_keywords(
            conn, campanha_id, extracao.get("keywords_eixos") or {}
        )
    except Exception:
        stats["eixos_kw"] = 0

    for tm in list(extracao.get("temas_proprio") or []) + list(
        extracao.get("temas_adversario") or []
    ):
        nm_t = (tm.get("nome") or "").strip()
        if not nm_t:
            continue
        existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
        if _existe(existentes, nome=nm_t):
            continue
        try:
            radar_store.upsert_alvo(
                conn,
                campanha_id,
                kind="tema",
                nome=nm_t,
                query_news=(tm.get("query_news") or nm_t)[:300],
                handle_ig=None,
                is_own=False,
                papel=tm.get("papel") or "tema",
                prioridade=4,
                notas=(tm.get("eixo") or "")[:200],
            )
            added += 1
            stats["tema"] += 1
        except Exception:
            continue

    return {
        "ok": True,
        "added": added,
        "candidato": nome,
        "partido": partido,
        "uf": uf,
        "stats": stats,
        "plano_chars": extracao.get("plano_chars") or 0,
        "plano_proprio_encontrado": bool(extracao.get("plano_chars")),
    }
