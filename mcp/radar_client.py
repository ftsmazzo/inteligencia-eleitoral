"""Cliente clima — store Radar (ctl.radar_*) primeiro; motores livres; painel legado opcional.

Sempre retorna nivel=indicio. Cifra no texto é pista, não fato.
"""
from __future__ import annotations

import html as html_module
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

_DEFAULT_URL = "https://inteligencia-eleitora-painel.kxryyk.easypanel.host"


def _base() -> str:
    return (os.environ.get("RADAR_API_URL") or _DEFAULT_URL).rstrip("/")


def _use_legacy_painel() -> bool:
    return (os.environ.get("RADAR_USE_LEGACY_PAINEL") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json, text/html;q=0.9", "User-Agent": "inteligencia-eleitoral-mcp/0.2"}
    tok = (os.environ.get("RADAR_API_TOKEN") or "").strip()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _unescape(s: str) -> str:
    return html_module.unescape(re.sub(r"\s+", " ", s or "")).strip()


def _sanitizar_url(it: dict[str, Any]) -> dict[str, Any]:
    u = it.get("url")
    if not isinstance(u, str) or not u.strip():
        it["url"] = None
        return it
    u = u.strip()
    monstro = "news.google.com" in u or len(u) > 140
    if monstro:
        it["url_raw"] = u
        it["url"] = None
    else:
        it["url"] = u
    return it


def _parse_articles(html: str) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for block in re.finditer(r"<article class=['\"]item['\"][^>]*>(.*?)</article>", html, re.I | re.S):
        chunk = block.group(1)
        m_title = re.search(r"<strong>(.*?)</strong>", chunk, re.S)
        m_link = re.search(r"<a href=['\"]([^'\"]+)['\"][^>]*>\s*<strong>", chunk, re.S)
        m_meta = re.search(r"<div class=muted>(.*?)</div>", chunk, re.S)
        badges = [_unescape(b) for b in re.findall(r"<span class=bad>(.*?)</span>", chunk, re.S)]
        m_clima = re.search(r"clima\s*(-?\d+).*?risco\s*([^<]+)", chunk, re.I | re.S)
        m_p = re.search(r"<p>(.*?)</p>", chunk, re.S)
        meta_txt = _unescape(re.sub(r"<[^>]+>", " ", m_meta.group(1))) if m_meta else ""
        partes = [p.strip() for p in re.split(r"[·|]", meta_txt) if p.strip()]
        canal = partes[0] if partes else None
        fonte = partes[1] if len(partes) > 1 else None
        origem = partes[2] if len(partes) > 2 else None
        alvo = partes[3] if len(partes) > 3 else None
        quando = partes[4] if len(partes) > 4 else None
        if not quando:
            m_q = re.search(r"\b(\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2})\b", meta_txt)
            quando = m_q.group(1) if m_q else None
        rotulo = " · ".join(p for p in (fonte, quando) if p) or meta_txt or None
        item = {
            "titulo": _unescape(m_title.group(1)) if m_title else "",
            "url": m_link.group(1) if m_link else None,
            "canal": canal,
            "fonte": fonte,
            "origem": origem,
            "alvo": alvo,
            "quando": quando,
            "data_hora": quando,
            "rotulo": rotulo,
            "tipo": next(
                (
                    b
                    for b in badges
                    if b
                    in {
                        "ataque",
                        "defesa",
                        "escandalo",
                        "escândalo",
                        "rotina",
                        "oportunidade",
                        "boato",
                        "cobertura",
                        "mobilizacao",
                        "mobilização",
                    }
                ),
                badges[2] if len(badges) > 2 else None,
            ),
            "tom": badges[0] if badges else None,
            "urgencia": badges[1] if len(badges) > 1 else None,
            "badges": badges,
            "clima_score": int(m_clima.group(1)) if m_clima else None,
            "risco": _unescape(m_clima.group(2)) if m_clima else None,
            "resumo": _unescape(m_p.group(1)) if m_p else "",
        }
        itens.append(_sanitizar_url(item))
    return itens


def _normalizar_item_json(raw: dict[str, Any]) -> dict[str, Any]:
    it = dict(raw)
    fonte = it.get("fonte") or it.get("source") or it.get("veiculo")
    quando = (
        it.get("quando")
        or it.get("data_hora")
        or it.get("publicado_em")
        or it.get("published_at")
        or it.get("hora")
    )
    if isinstance(quando, (int, float)):
        try:
            quando = datetime.fromtimestamp(quando, tz=timezone.utc).strftime("%d/%m %H:%M")
        except (OSError, OverflowError, ValueError):
            quando = str(quando)
    elif quando is not None:
        quando = str(quando).strip() or None
        if quando and "T" in quando:
            try:
                dt = datetime.fromisoformat(quando.replace("Z", "+00:00"))
                from zoneinfo import ZoneInfo

                quando = dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m %H:%M")
            except ValueError:
                pass
    if fonte is not None:
        fonte = str(fonte).strip() or None
    it["fonte"] = fonte
    it["quando"] = quando
    it["data_hora"] = quando
    if not it.get("rotulo"):
        it["rotulo"] = " · ".join(p for p in (fonte, quando) if p) or None
    it["nivel"] = "indicio"
    return _sanitizar_url(it)


def _filter_janela(itens: list[dict[str, Any]], janela_horas: int | None) -> list[dict[str, Any]]:
    if not janela_horas or janela_horas <= 0:
        return itens
    agora = datetime.now(timezone.utc)
    corte = agora - timedelta(hours=janela_horas)
    out: list[dict[str, Any]] = []
    for it in itens:
        q = it.get("quando") or ""
        m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", str(q))
        if not m:
            out.append(it)
            continue
        dia, mes, hora, minuto = map(int, m.groups())
        try:
            dt = datetime(agora.year, mes, dia, hora, minuto, tzinfo=timezone.utc)
        except ValueError:
            out.append(it)
            continue
        if dt >= corte:
            out.append(it)
    return out


def _consultar_store(
    campanha_id: str,
    *,
    q: str | None,
    canal: str | None,
    origem: str | None,
    tipo: str | None,
    urgencia: str | None,
    janela_horas: int | None,
    page: int,
    limite: int,
) -> dict[str, Any] | None:
    import os

    import psycopg

    from radar import store
from radar.schema import ensure_schema

    url = os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")
    if not url:
        return None
    try:
        ensure_schema()
        with psycopg.connect(url) as conn:
            data = store.stream(
                conn,
                campanha_id,
                q=q,
                canal=canal,
                origem=origem,
                tipo=tipo,
                urgencia=urgencia,
                janela_horas=janela_horas,
                page=page,
                limite=limite,
            )
            conn.commit()
        return data
    except Exception:
        return None


async def consultar_clima(
    *,
    q: str | None = None,
    canal: str | None = None,
    origem: str | None = None,
    tipo: str | None = None,
    urgencia: str | None = None,
    janela_horas: int | None = 168,
    campaign_id: int | None = None,
    campanha_id: str | None = None,
    page: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    """Store Radar (uuid) → motores livres → painel legado (opt-in)."""
    from clima_motores import (
        buscar_instagram_apify,
        buscar_news_google,
        resolver_handle_instagram,
    )

    if q:
        q = q.strip()
        if q.startswith("@"):
            q = q.lstrip("@").strip()
        m_ig = re.search(r"(?:instagram\.com/)?@?([A-Za-z0-9._]+)/?$", q)
        if m_ig and " " not in q and ("instagram" in q.lower() or q.count("/") >= 1):
            q = m_ig.group(1)

    canal_l = (canal or "").strip().lower() or None
    horas = janela_horas if janela_horas is not None else 168
    lim = max(1, min(limite or 20, 50))
    params: dict[str, Any] = {"page": max(1, page)}
    if q:
        params["q"] = q
    if canal_l:
        params["canal"] = canal_l
    if origem:
        params["origem"] = origem.strip().lower()
    if tipo:
        params["tipo"] = tipo.strip().lower()
    if urgencia:
        params["urgencia"] = urgencia.strip().lower()

    itens: list[dict[str, Any]] = []
    motores: list[str] = []
    avisos: list[str] = []
    modo = "motores_livres"

    # 0) Store interno (ctl.radar_*) — caminho feliz por campanha Apura
    if campanha_id:
        import asyncio

        stored = await asyncio.to_thread(
            _consultar_store,
            campanha_id,
            q=q,
            canal=canal_l,
            origem=origem.strip().lower() if origem else None,
            tipo=tipo.strip().lower() if tipo else None,
            urgencia=urgencia.strip().lower() if urgencia else None,
            janela_horas=horas,
            page=max(1, page),
            limite=lim,
        )
        if stored and stored.get("itens"):
            itens = [_normalizar_item_json(x) for x in stored["itens"] if isinstance(x, dict)]
            motores.append("radar_store")
            modo = "radar_store"
            nota = (
                "Camada C (store Radar / ctl.radar_*): clima da campanha Apura. "
                "nivel=indicio. Cite fonte + data_hora/rotulo."
            )
            return {
                "status": "ok",
                "nivel": "indicio",
                "nota_metodologica": nota,
                "modo": modo,
                "motores": motores,
                "filtro": params,
                "janela_horas": horas,
                "campanha_id": campanha_id,
                "total": stored.get("total"),
                "page": stored.get("page"),
                "pages": stored.get("pages"),
                "itens": itens,
            }
        if stored is not None:
            avisos.append("radar_store vazio nesta janela/filtro")

    import asyncio

    quer_news = canal_l in (None, "", "news", "noticia", "notícia") and bool(q)
    if quer_news and canal_l != "instagram":
        try:
            news = await asyncio.to_thread(
                buscar_news_google, q or "", janela_horas=horas or 168, limite=lim
            )
            if news:
                itens.extend(news)
                motores.append("google_news_rss")
        except Exception as e:
            avisos.append(f"news: {type(e).__name__}")

    if canal_l == "instagram":
        handle = resolver_handle_instagram(q) if q else None
        if handle:
            try:
                ig = await asyncio.to_thread(
                    buscar_instagram_apify,
                    handle,
                    janela_horas=horas or 168,
                    limite=min(lim, 12),
                )
                if ig:
                    itens.extend(ig)
                    motores.append("apify_instagram")
                else:
                    avisos.append(f"instagram @{handle}: zero posts na janela")
            except Exception as e:
                avisos.append(f"instagram: {type(e).__name__}: {e}")
        else:
            avisos.append(
                "Informe um @handle (ex.: @lulaoficial) ou nome com alias conhecido (Lula → lulaoficial)."
            )

    # Painel legado só com opt-in ou campaign_id numérico explícito
    usar_painel = _use_legacy_painel() or campaign_id is not None
    if usar_painel and not itens:
        url = f"{_base()}/?{urlencode(params)}"
        cookies: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            if campaign_id is not None:
                await client.post(f"{_base()}/campanha", data={"cid": str(campaign_id)})
                cookies = dict(client.cookies)
            r = await client.get(url, headers=_headers(), cookies=cookies or None)
        if r.status_code < 400:
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                data = r.json()
                raw = data.get("itens") or data.get("items") or data.get("stream") or []
                if isinstance(raw, list):
                    itens.extend(
                        [_normalizar_item_json(x) if isinstance(x, dict) else x for x in raw]
                    )
            else:
                itens.extend(_parse_articles(r.text))
            motores.append("painel_radar_legado")
            modo = "motores+painel_legado"
        else:
            avisos.append(f"painel HTTP {r.status_code}")

    itens = _filter_janela(itens, horas)
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in itens:
        key = f"{it.get('canal')}|{it.get('titulo')}|{it.get('quando')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    itens = uniq[:lim]

    nota = (
        "Camada C (clima): store Radar por campanha e/ou Google News RSS / Apify Instagram. "
        "nivel=indicio. Cite fonte + data_hora/rotulo. Se url=null, não cole url_raw. "
        f"Motores: {', '.join(motores) or 'nenhum'}."
    )
    if avisos:
        nota += " Avisos: " + "; ".join(avisos)

    if not itens:
        msg = "Nenhum item de clima para este filtro."
        if avisos:
            msg += " " + "; ".join(avisos)
        return {
            "status": "vazio",
            "nivel": "indicio",
            "mensagem": msg,
            "nota_metodologica": nota,
            "modo": modo,
            "motores": motores,
            "filtro": params,
            "janela_horas": horas,
            "campanha_id": campanha_id,
            "itens": [],
        }

    return {
        "status": "ok",
        "nivel": "indicio",
        "nota_metodologica": nota,
        "modo": modo,
        "motores": motores,
        "filtro": params,
        "janela_horas": horas,
        "campanha_id": campanha_id,
        "itens": itens,
    }
