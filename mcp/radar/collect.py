"""Coleta Radar: RSS + Apify Instagram → store + classify (PULSO)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from radar import classify as clf
from radar import store

BRT = ZoneInfo("America/Sao_Paulo")
SLOTS = {8, 14, 20}
_POLL_LOCK = threading.Lock()
_LAST_SLOT_KEY: str | None = None

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina",
    "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}


def _query_com_escopo(q: str, uf: str | None) -> str:
    """Amarra a busca de notícias ao estado da campanha (evita trazer Brasil todo
    p/ nomes comuns/genéricos, ex.: temas ou políticos nacionais homônimos)."""
    q = (q or "").strip()
    if not uf:
        return q
    uf = uf.strip().upper()
    nome_uf = UF_NOME.get(uf, "")
    if not nome_uf:
        return q
    # A sigla (ex.: "AP") sozinha não ajuda o texto do Google News — o nome do
    # estado por extenso é o sinal que realmente restringe a busca geográfica.
    ja_tem_nome = nome_uf.lower() in q.lower()
    if ja_tem_nome:
        return q
    return f"{q} {nome_uf}"


def _since_for_alvo(last_seen: str | None) -> datetime:
    if last_seen:
        try:
            dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc) - timedelta(hours=4)


def _ingest_raw(
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
    entity_kind: str | None,
    eixos: list[tuple[str, str]],
) -> bool:
    item_id = store.insert_item(
        conn,
        campanha_id,
        origem=origem,
        canal=canal,
        fonte=fonte,
        url=url,
        titulo=titulo,
        body=body,
        published_at=published_at,
        entity_name=entity_name,
        entity_kind=entity_kind,
    )
    if not item_id:
        return False
    if origem == "oficial":
        a = clf.classify_mix(titulo, body, eixos)
    else:
        a = clf.classify_clima(titulo, body, entity_name or "")
    store.save_analise(conn, item_id, a)
    return True


def _parse_quando_to_dt(quando: str | None) -> datetime | None:
    if not quando:
        return None
    import re

    m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", quando.strip())
    if not m:
        return None
    dia, mes, hora, minuto = map(int, m.groups())
    agora = datetime.now(timezone.utc)
    try:
        return datetime(agora.year, mes, dia, hora, minuto, tzinfo=timezone.utc)
    except ValueError:
        return None


def collect_campanha(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    mode: str = "manual",
    janela_horas: int = 96,
) -> dict[str, Any]:
    from clima_motores import buscar_instagram_apify, buscar_news_google

    cfg = store.get_config(conn, campanha_id)
    uf_campanha = (cfg.get("uf") or "").strip().upper() or None

    store.ensure_eixos(conn, campanha_id)
    eixos_rows = store.list_eixos(conn, campanha_id)
    eixos = []
    for e in eixos_rows:
        if not e["enabled"]:
            continue
        dica = (e.get("hint") or "").strip()
        kws = (e.get("keywords") or "").strip()
        catalog = dica
        if kws:
            catalog = f"{dica} | palavras-chave: {kws}" if dica else kws
        eixos.append((e["name"], catalog))
    alvos = store.list_alvos(conn, campanha_id, ativo_only=True)
    run_id = store.start_run(conn, campanha_id, mode)
    novos = 0
    errs: list[str] = []
    stats = {"news": 0, "ig_oficial": 0, "ig_clima": 0}

    if not alvos:
        store.finish_run(conn, run_id, ok=0, err="nenhum alvo ativo — configure em Alvos")
        return {"run_id": run_id, "novos": 0, "err": "nenhum alvo ativo", "alvos": 0}

    for alvo in alvos:
        nome = alvo["nome"]
        kind = alvo["kind"]
        is_own = bool(alvo["is_own"])
        since = _since_for_alvo(alvo.get("last_seen_at"))
        horas = max(
            4,
            int((datetime.now(timezone.utc) - since).total_seconds() // 3600) + 1,
        )
        horas = min(horas, max(24, janela_horas))

        # News: pessoa, adversario, tema (e perfil com query_news)
        q = (alvo.get("query_news") or "").strip()
        if not q and kind in ("pessoa", "adversario", "tema"):
            q = nome
        if q and kind in ("pessoa", "adversario", "tema"):
            q_uf = _query_com_escopo(q, uf_campanha)
            try:
                news = buscar_news_google(q_uf, janela_horas=horas, limite=12)
                for it in news:
                    pub = _parse_quando_to_dt(it.get("quando")) or datetime.now(timezone.utc)
                    if pub <= since:
                        continue
                    ok = _ingest_raw(
                        conn,
                        campanha_id,
                        origem="clima",
                        canal=it.get("canal") or "news",
                        fonte=it.get("fonte"),
                        url=it.get("url") or it.get("url_raw"),
                        titulo=it.get("titulo") or "",
                        body=it.get("resumo") or "",
                        published_at=pub,
                        entity_name=nome,
                        entity_kind=kind,
                        eixos=eixos,
                    )
                    if ok:
                        novos += 1
                        stats["news"] += 1
            except Exception as e:
                errs.append(f"news:{nome}:{type(e).__name__}")

        # Instagram: perfil (obrigatório) ou pessoa/adversario com handle
        handle = (alvo.get("handle_ig") or "").strip().lstrip("@")
        if handle and (kind == "perfil" or kind in ("pessoa", "adversario")):
            origem = "oficial" if (kind == "perfil" and is_own) else "clima"
            try:
                ig = buscar_instagram_apify(handle, janela_horas=horas, limite=10)
                for it in ig:
                    pub = _parse_quando_to_dt(it.get("quando")) or datetime.now(timezone.utc)
                    if pub <= since:
                        continue
                    ok = _ingest_raw(
                        conn,
                        campanha_id,
                        origem=origem,
                        canal="instagram",
                        fonte="Instagram",
                        url=it.get("url") or it.get("url_raw"),
                        titulo=it.get("titulo") or f"Post @{handle}",
                        body=it.get("resumo") or "",
                        published_at=pub,
                        entity_name=f"@{handle}" if origem == "clima" else nome,
                        entity_kind="oficial" if origem == "oficial" else kind,
                        eixos=eixos,
                    )
                    if ok:
                        novos += 1
                        if origem == "oficial":
                            stats["ig_oficial"] += 1
                        else:
                            stats["ig_clima"] += 1
            except Exception as e:
                errs.append(f"ig:@{handle}:{type(e).__name__}:{e}")

        store.mark_alvo_seen(conn, alvo["id"])

    err = "; ".join(errs[:8]) if errs else None
    store.finish_run(conn, run_id, ok=novos, err=err)
    return {
        "run_id": run_id,
        "novos": novos,
        "err": err,
        "alvos": len(alvos),
        "mode": mode,
        "stats": stats,
    }


def collect_all_campanhas(conn: psycopg.Connection, *, mode: str = "slot") -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id::text FROM ctl.campanha WHERE ativo IS TRUE ORDER BY nome"
    ).fetchall()
    out = []
    for (cid,) in rows:
        out.append(collect_campanha(conn, cid, mode=mode))
    return out


def maybe_run_slot(conn_factory) -> dict[str, Any] | None:
    global _LAST_SLOT_KEY
    now = datetime.now(BRT)
    if now.hour not in SLOTS or now.minute > 20:
        return None
    key = now.strftime("%Y-%m-%d-%H")
    if key == _LAST_SLOT_KEY:
        return None
    if not _POLL_LOCK.acquire(blocking=False):
        return None
    try:
        if key == _LAST_SLOT_KEY:
            return None
        with conn_factory() as conn:
            results = collect_all_campanhas(conn, mode=f"slot-{now.hour}")
            conn.commit()
        _LAST_SLOT_KEY = key
        return {"slot": now.hour, "results": results}
    finally:
        _POLL_LOCK.release()
