"""Upload HTML de dossiê → blocos ctl.campanha_memoria."""
from __future__ import annotations

import re
from html import unescape
from typing import Any

from gestao import memoria

_TAG_RE = re.compile(r"<[^>]+>", re.S)
_WS_RE = re.compile(r"\s+")


def _texto(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = _TAG_RE.sub(" ", t)
    t = unescape(t)
    return _WS_RE.sub(" ", t).strip()


def _secionar(html: str) -> list[tuple[str, str]]:
    """Parte por <section> ou h2."""
    parts: list[tuple[str, str]] = []
    sections = re.findall(r"(?is)<section[^>]*>(.*?)</section>", html)
    if sections:
        for sec in sections:
            title_m = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", sec)
            title = _texto(title_m.group(1)) if title_m else "Bloco do dossiê"
            body = _texto(sec)
            if len(body) > 80:
                parts.append((title[:200], body))
        if parts:
            return parts
    # fallback h2
    chunks = re.split(r"(?is)<h2[^>]*>", html)
    for ch in chunks[1:]:
        title_m = re.match(r"(?is)(.*?)</h2>(.*)", ch, re.S)
        if not title_m:
            continue
        title = _texto(title_m.group(1))
        body = _texto(title_m.group(2))
        if len(body) > 80:
            parts.append((title[:200] or "Bloco", body))
    if parts:
        return parts
    full = _texto(html)
    if len(full) > 80:
        # fatia em ~3500 chars
        i = 0
        n = 1
        while i < len(full):
            parts.append((f"Dossiê parte {n}", full[i : i + 3500]))
            i += 3500
            n += 1
    return parts


def _tipo_titulo(titulo: str) -> str:
    t = (titulo or "").lower()
    if "pesquisa" in t:
        return "dossie_pesquisas"
    if "trajet" in t or "personagem" in t or "biograf" in t:
        return "dossie_personagem"
    if "municíp" in t or "municip" in t or "geografia" in t:
        return "dossie_territorio"
    if "síntese" in t or "sintese" in t or "estratég" in t or "estrateg" in t:
        return "dossie_sintese"
    if "eleiç" in t or "eleic" in t or "histórico" in t or "historico" in t:
        return "dossie_historico"
    if "governo" in t or "realiza" in t:
        return "dossie_governo"
    return "dossie"


def ingerir_html(conn, campanha_id: str, html: str, *, nome_arquivo: str = "dossie.html") -> dict[str, Any]:
    if not html or len(html) < 40:
        raise ValueError("HTML vazio ou muito curto")
    # remove dossiês anteriores
    conn.execute(
        """
        DELETE FROM ctl.campanha_memoria
        WHERE campanha_id = %s::uuid AND (tipo = 'dossie' OR tipo LIKE 'dossie_%%')
        """,
        (campanha_id,),
    )
    secoes = _secionar(html)
    ids = []
    for titulo, corpo in secoes:
        tipo = _tipo_titulo(titulo)
        ids.append(
            memoria.upsert_bloco(
                conn,
                campanha_id,
                tipo=tipo,
                titulo=titulo,
                corpo=corpo[:12000],
                fonte=f"upload:{nome_arquivo}",
                nivel="indicio",
                meta={"arquivo": nome_arquivo},
            )
        )
    return {"ok": True, "blocos": len(ids), "ids": ids}
