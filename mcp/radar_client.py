"""Cliente do Radar Eleitoral — consulta livre (não travada em candidato).

O painel atual responde HTML em GET /. Este módulo:
1. Tenta JSON (se o Radar passar a expor)
2. Faz parse dos <article class='item'> do HTML

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


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json, text/html;q=0.9", "User-Agent": "inteligencia-eleitoral-mcp/0.1"}
    tok = (os.environ.get("RADAR_API_TOKEN") or "").strip()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _unescape(s: str) -> str:
    return html_module.unescape(re.sub(r"\s+", " ", s or "")).strip()


def _sanitizar_url(it: dict[str, Any]) -> dict[str, Any]:
    """Evita URLs monstro (Google News RSS) estourarem o chat do Apura."""
    u = it.get("url")
    if not isinstance(u, str) or not u.strip():
        it["url"] = None
        return it
    u = u.strip()
    monstro = "news.google.com" in u or len(u) > 140
    if monstro:
        it["url_raw"] = u
        it["url"] = None  # redator/UI: sem link longo
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
        # meta: "news · UOL · clima · Lula · 27/08 07:56"
        partes = [p.strip() for p in re.split(r"[·|]", meta_txt) if p.strip()]
        canal = partes[0] if partes else None
        fonte = partes[1] if len(partes) > 1 else None
        origem = partes[2] if len(partes) > 2 else None
        alvo = partes[3] if len(partes) > 3 else None
        quando = partes[4] if len(partes) > 4 else None
        # Se o parse por posição falhar, tenta achar dd/mm HH:MM no meta
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
            "tipo": next((b for b in badges if b in {
                "ataque", "defesa", "escandalo", "escândalo", "rotina",
                "oportunidade", "boato", "cobertura", "mobilizacao", "mobilização",
            }), badges[2] if len(badges) > 2 else None),
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
    """Garante fonte + data/hora também quando o Radar devolver JSON."""
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
    if fonte is not None:
        fonte = str(fonte).strip() or None
    it["fonte"] = fonte
    it["quando"] = quando
    it["data_hora"] = quando
    if not it.get("rotulo"):
        it["rotulo"] = " · ".join(p for p in (fonte, quando) if p) or None
    return _sanitizar_url(it)


def _filter_janela(itens: list[dict[str, Any]], janela_horas: int | None) -> list[dict[str, Any]]:
    """Filtro aproximado pelo campo 'quando' (dd/mm HH:MM) do painel — ano corrente UTC."""
    if not janela_horas or janela_horas <= 0:
        return itens
    agora = datetime.now(timezone.utc)
    corte = agora - timedelta(hours=janela_horas)
    out: list[dict[str, Any]] = []
    for it in itens:
        q = it.get("quando") or ""
        m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", q)
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


async def consultar_clima(
    *,
    q: str | None = None,
    canal: str | None = None,
    origem: str | None = None,
    tipo: str | None = None,
    urgencia: str | None = None,
    janela_horas: int | None = 168,
    campaign_id: int | None = None,
    page: int = 1,
    limite: int = 20,
) -> dict[str, Any]:
    """Consulta sob demanda: 'notícia do Flávio esta semana', 'Instagram do Lula', etc."""
    # Normaliza @handle → texto de busca
    if q:
        q = q.strip()
        if q.startswith("@"):
            q = q.lstrip("@").strip()
        # "instagram.com/lulaoficial" → lulaoficial
        m_ig = re.search(r"(?:instagram\.com/)?@?([A-Za-z0-9._]+)/?$", q)
        if m_ig and " " not in q and ("instagram" in q.lower() or q.count("/") >= 1):
            q = m_ig.group(1)

    params: dict[str, Any] = {"page": max(1, page)}
    if q:
        params["q"] = q
    if canal:
        params["canal"] = canal.strip().lower()
    if origem:
        params["origem"] = origem.strip().lower()
    if tipo:
        params["tipo"] = tipo.strip().lower()
    if urgencia:
        params["urgencia"] = urgencia.strip().lower()

    url = f"{_base()}/?{urlencode(params)}"
    cookies: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        if campaign_id is not None:
            # painel usa form POST /campanha com cid — cookie de sessão
            await client.post(f"{_base()}/campanha", data={"cid": str(campaign_id)})
            cookies = dict(client.cookies)
        r = await client.get(url, headers=_headers(), cookies=cookies or None)

    if r.status_code >= 400:
        return {
            "status": "erro",
            "nivel": "indicio",
            "mensagem": f"Radar HTTP {r.status_code}",
            "itens": [],
        }

    ct = (r.headers.get("content-type") or "").lower()
    itens: list[dict[str, Any]] = []
    modo = "html"

    if "application/json" in ct:
        modo = "json"
        data = r.json()
        raw = data.get("itens") or data.get("items") or data.get("stream") or []
        if isinstance(raw, list):
            itens = [_normalizar_item_json(x) if isinstance(x, dict) else x for x in raw]
    else:
        itens = _parse_articles(r.text)

    itens = _filter_janela(itens, janela_horas)
    itens = itens[: max(1, min(limite, 50))]

    nota = (
        "Camada C (Radar): clima de redes/notícias. nivel=indicio — "
        "não use cifra do texto como fato eleitoral. "
        "Em cada item use fonte + data_hora/quando (campo rotulo) ao citar, como no painel Radar. "
        "Se url estiver null, NÃO invente nem cole url_raw (links Google News são omitidos de propósito). "
        "Instagram só retorna perfis/alvos cadastrados nas campanhas do painel Radar."
    )
    if not itens:
        msg = "Nenhum item no Radar para este filtro."
        if (canal or "").lower() == "instagram":
            msg = (
                "Nenhum post de Instagram no Radar para este filtro. "
                "O painel só monitora perfis cadastrados nas campanhas ativas — "
                "se @/perfil não estiver cadastrado, o resultado é vazio (não é falha de acesso)."
            )
        return {
            "status": "vazio",
            "nivel": "indicio",
            "mensagem": msg,
            "nota_metodologica": nota,
            "modo": modo,
            "filtro": params,
            "janela_horas": janela_horas,
            "itens": [],
        }

    return {
        "status": "ok",
        "nivel": "indicio",
        "nota_metodologica": nota,
        "modo": modo,
        "filtro": params,
        "janela_horas": janela_horas,
        "itens": itens,
    }
