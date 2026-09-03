"""Seed Radar a partir do escopo Gestão + redes TSE (próprio e adversários)."""
from __future__ import annotations

from typing import Any

import psycopg

from gestao import memoria
from gestao.store import get_status
from radar import store as radar_store


def _existe(existentes: list[dict[str, Any]], *, nome: str | None = None, handle: str | None = None) -> bool:
    if handle:
        h = handle.lower().lstrip("@")
        if any((a.get("handle_ig") or "").lower() == h for a in existentes):
            return True
    if nome:
        if any((a.get("nome") or "") == nome for a in existentes):
            return True
    return False


def seed_radar_da_gestao(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    if not st.get("nm_urna") and not st.get("nm_candidato"):
        raise ValueError("Escopo sem candidato")

    nome = st.get("nm_urna") or st.get("nm_candidato")
    uf = st.get("sg_uf")
    cargo = st.get("cargo_label") or ""
    partido = st.get("sg_partido")

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

    if not any(
        a["nome"] == nome and a["kind"] == "pessoa"
        for a in radar_store.list_alvos(conn, campanha_id, ativo_only=False)
    ):
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
        )
        added += 1

    pessoas: list[dict[str, Any]] = []
    blocos = memoria.listar(conn, campanha_id, tipo="base_redes", limite=3)
    for b in blocos:
        meta = b.get("meta") or {}
        pessoas.extend(meta.get("pessoas") or [])

    if pessoas:
        for p in pessoas:
            papel = p.get("papel") or "adversario"
            nm = (p.get("nm_urna") or "").strip()
            igs = [h for h in (p.get("ig") or []) if h]
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if papel == "adversario" and nm and nm != nome and not _existe(existentes, nome=nm):
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="adversario",
                    nome=nm,
                    query_news=f"{nm} {uf or ''}".strip(),
                    handle_ig=igs[0] if igs else None,
                    is_own=False,
                    papel="adversario",
                    prioridade=2,
                    notas=(p.get("sg_partido") or ""),
                )
                added += 1
            for h in igs:
                existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
                if _existe(existentes, handle=h):
                    continue
                if (h or "").lower() in {"channel", "share", "instagram", "www"}:
                    continue
                proprio = papel == "proprio"
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="perfil",
                    nome=f"{'Instagram oficial' if proprio else 'IG adversário'} @{h}",
                    query_news="" if proprio else f"{nm} {uf or ''}".strip(),
                    handle_ig=h,
                    is_own=proprio,
                    papel="proprio" if proprio else "adversario",
                    prioridade=1 if proprio else 2,
                )
                added += 1
    else:
        # fallback: IGs soltos + concorrentes no texto
        handles = []
        for b in blocos:
            handles.extend((b.get("meta") or {}).get("ig") or [])
        for h in handles:
            if not h:
                continue
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if _existe(existentes, handle=h):
                continue
            radar_store.upsert_alvo(
                conn,
                campanha_id,
                kind="perfil",
                nome=f"Instagram oficial @{h}",
                query_news="",
                handle_ig=h,
                is_own=True,
                papel="proprio",
                prioridade=1,
            )
            added += 1
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

    return {"ok": True, "added": added, "candidato": nome, "partido": partido, "uf": uf}
