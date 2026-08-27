"""Motores livres de clima (sem trava de campaign_id do painel Radar).

- Notícias: Google News RSS (igual ao Radar)
- Instagram: Apify (actor configurável), sob demanda por @handle

Sempre nivel=indicio. Não grava no banco do Radar.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx

# Aliases comuns → handle Instagram (consulta livre)
_IG_ALIASES: dict[str, str] = {
    "lula": "lulaoficial",
    "lulaoficial": "lulaoficial",
    "bolsonaro": "jairmessiasbolsonaro",
    "jairbolsonaro": "jairmessiasbolsonaro",
    "flaviobolsonaro": "flaviobolsonaro",
    "flavio": "flaviobolsonaro",
    "caiado": "ronaldocaiado",
    "ronaldocaiado": "ronaldocaiado",
    "zema": "romeuzema",
    "romeuzema": "romeuzema",
}


def _apify_token() -> str:
    return (os.environ.get("APIFY_TOKEN") or "").strip()


def _apify_ig_actor() -> str:
    raw = (os.environ.get("APIFY_IG_ACTOR") or "apify/instagram-scraper").strip()
    return raw.replace("/", "~")


def resolver_handle_instagram(q: str | None) -> str | None:
    if not q:
        return None
    s = q.strip()
    s = re.sub(r"^https?://(www\.)?instagram\.com/", "", s, flags=re.I)
    s = s.strip("/").lstrip("@").split("/")[0].split("?")[0].strip()
    if not s:
        return None
    key = re.sub(r"[^a-z0-9._]", "", s.lower())
    if key in _IG_ALIASES:
        return _IG_ALIASES[key]
    # handle tipico
    if re.fullmatch(r"[A-Za-z0-9._]{2,40}", s) and " " not in s:
        return s.lstrip("@")
    # nome composto → tenta alias pela primeira palavra
    first = key.split()[0] if key else ""
    return _IG_ALIASES.get(first)


def _sanitizar_url(url: str | None) -> tuple[str | None, str | None]:
    """Retorna (url_exibivel, url_raw). Omite monstro Google News."""
    if not url or not str(url).strip():
        return None, None
    u = str(url).strip()
    if "news.google.com" in u or len(u) > 140:
        return None, u
    return u, None


def _rotulo(fonte: str | None, quando: str | None) -> str | None:
    return " · ".join(p for p in (fonte, quando) if p) or None


def _fmt_quando(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%d/%m %H:%M")


def buscar_news_google(
    q: str,
    *,
    janela_horas: int = 168,
    limite: int = 20,
) -> list[dict[str, Any]]:
    """Coleta livre via RSS do Google News — sem campanha."""
    q = (q or "").strip()
    if not q:
        return []
    horas = janela_horas if janela_horas and janela_horas > 0 else 168
    since = datetime.now(timezone.utc) - timedelta(hours=horas)
    query = f"{q} after:{since.date().isoformat()}"
    url = (
        "https://news.google.com/rss/search?q=%s&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        % quote_plus(query)
    )
    r = httpx.get(url, timeout=30.0, headers={"User-Agent": "inteligencia-eleitoral-clima/0.2"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    itens: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        if len(itens) >= max(1, min(limite, 50)):
            break
        title = unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        desc = unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        desc = re.sub(r"\s+", " ", desc).strip()
        fonte = (item.findtext("source") or "Google News").strip() or "Google News"
        try:
            pub = parsedate_to_datetime(item.findtext("pubDate") or "")
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            else:
                pub = pub.astimezone(timezone.utc)
        except Exception:
            pub = datetime.now(timezone.utc)
        if pub < since:
            continue
        if not title:
            continue
        url_ok, url_raw = _sanitizar_url(link)
        quando = _fmt_quando(pub)
        itens.append(
            {
                "titulo": title,
                "url": url_ok,
                "url_raw": url_raw,
                "canal": "news",
                "fonte": fonte,
                "origem": "clima",
                "alvo": q,
                "quando": quando,
                "data_hora": quando,
                "rotulo": _rotulo(fonte, quando),
                "tipo": "cobertura",
                "tom": None,
                "urgencia": None,
                "badges": [],
                "clima_score": None,
                "risco": None,
                "resumo": desc[:500] if desc else title,
                "motor": "google_news_rss",
            }
        )
    return itens


def _ig_permalink(row: dict[str, Any]) -> str:
    link = (row.get("url") or row.get("displayUrl") or "").strip()
    if "/p/" in link or "/reel/" in link or "/tv/" in link:
        return link.split("?")[0].rstrip("/") + "/"
    code = str(row.get("shortCode") or row.get("shortcode") or row.get("code") or "").strip()
    if code and code.lower() not in ("none", "null"):
        kind = "reel" if (row.get("type") or "").lower() in ("video", "reel", "clips") else "p"
        if row.get("productType") == "clips" or row.get("isReel"):
            kind = "reel"
        return f"https://www.instagram.com/{kind}/{code}/"
    return ""


def _ig_caption(row: dict[str, Any]) -> str:
    cap = row.get("caption")
    if isinstance(cap, dict):
        cap = cap.get("text") or ""
    return (cap or row.get("alt") or row.get("accessibilityCaption") or "").strip()


def _ig_when(row: dict[str, Any]) -> datetime | None:
    ts = row.get("timestamp") or row.get("takenAtTimestamp") or row.get("taken_at")
    if isinstance(ts, (int, float)) and ts > 10_000_000:
        try:
            return datetime.fromtimestamp(
                ts if ts < 10_000_000_000 else ts / 1000, tz=timezone.utc
            )
        except (OSError, OverflowError, ValueError):
            pass
    if ts:
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def _ig_expand(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        nested = row.get("latestPosts") or row.get("latestIgtvVideos") or row.get("posts") or []
        if nested:
            out.extend(nested)
        else:
            out.append(row)
    return out


def buscar_instagram_apify(
    handle: str,
    *,
    janela_horas: int = 168,
    limite: int = 12,
) -> list[dict[str, Any]]:
    """Coleta livre via Apify — qualquer @handle, sem cadastro no painel."""
    token = _apify_token()
    if not token:
        raise RuntimeError("APIFY_TOKEN não configurado no mcp-api")
    handle = handle.strip().lstrip("@")
    horas = janela_horas if janela_horas and janela_horas > 0 else 168
    since = datetime.now(timezone.utc) - timedelta(hours=horas)
    since_s = since.strftime("%Y-%m-%d")
    profile = f"https://www.instagram.com/{handle}/"
    actor = _apify_ig_actor()
    api = (
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
        f"?token={token}"
    )
    payload = {
        "directUrls": [profile],
        "resultsType": "posts",
        "resultsLimit": max(1, min(limite, 24)),
        "onlyPostsNewerThan": since_s,
    }
    r = httpx.post(api, json=payload, timeout=180.0)
    r.raise_for_status()
    data = r.json()
    rows = data if isinstance(data, list) else []
    posts = _ig_expand(rows)
    itens: list[dict[str, Any]] = []
    for row in posts:
        if not isinstance(row, dict):
            continue
        when = _ig_when(row) or datetime.now(timezone.utc)
        if when < since:
            continue
        caption = _ig_caption(row)
        link = _ig_permalink(row) or profile
        titulo = (caption[:120] + "…") if len(caption) > 120 else (caption or f"Post @{handle}")
        quando = _fmt_quando(when)
        url_ok, url_raw = _sanitizar_url(link)
        itens.append(
            {
                "titulo": titulo,
                "url": url_ok or link,
                "url_raw": url_raw,
                "canal": "instagram",
                "fonte": "Instagram",
                "origem": "clima",
                "alvo": f"@{handle}",
                "quando": quando,
                "data_hora": quando,
                "rotulo": _rotulo("Instagram", quando),
                "tipo": "cobertura",
                "tom": None,
                "urgencia": None,
                "badges": [],
                "clima_score": None,
                "risco": None,
                "resumo": caption[:600] if caption else titulo,
                "motor": "apify_instagram",
            }
        )
        if len(itens) >= max(1, min(limite, 24)):
            break
    return itens
