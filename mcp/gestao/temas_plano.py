"""Extrai temas e palavras-chave do plano de governo (acervo) por sq_candidato exato.

Nível indício — heurística léxica sobre texto oficial do plano. Nunca casa por nome
solto (ILIKE) para evitar colar tema do adversário errado no candidato do escopo.
Sem sq_candidato confirmado, não gera tema — ausência é inexistente, não zero.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

import psycopg

# tema_label → (eixo_mix, keywords)
_LEXICO: list[tuple[str, str, list[str]]] = [
    ("Saúde", "Gestao e entregas", ["saude", "hospital", "ubs", "sus", "medico", "vacina"]),
    ("Educação", "Gestao e entregas", ["educacao", "escola", "universidade", "creche", "alfabetizacao"]),
    ("Infraestrutura", "Gestao e entregas", ["obra", "estrada", "ponte", "saneamento", "infraestrutura"]),
    ("Segurança", "Gestao e entregas", ["seguranca", "policia", "violencia", "crime"]),
    ("Emprego e renda", "Gestao e entregas", ["emprego", "renda", "trabalho", "economia", "industria"]),
    ("Meio ambiente", "Gestao e entregas", ["ambiente", "amazonia", "floresta", "clima", "sustentavel"]),
    ("Agricultura", "Territorio e interior", ["agricultura", "agronegocio", "rural", "produtor"]),
    ("Interior e municípios", "Territorio e interior", ["municipio", "interior", "cidade", "bairro", "prefeitura"]),
    ("Identidade e valores", "Identidade", ["familia", "fe", "trajetoria", "valores", "juventude"]),
    ("Mobilização", "Mobilizacao", ["voto", "urna", "campanha", "afiliacao", "mobilizacao"]),
]


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", (s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", t)


def _textos_plano_por_sq(
    conn: psycopg.Connection,
    *,
    sq_candidato: str | int,
    limite_chunks: int = 60,
) -> list[str]:
    """Só casa por sq_candidato exato no meta do documento — sem ILIKE de nome."""
    texts: list[str] = []
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(c.secao, '') || ' ' || left(COALESCE(c.texto, ''), 2500)
            FROM acervo.documento d
            JOIN acervo.chunk c ON c.documento_id = d.id
            WHERE d.ativo IS TRUE
              AND d.tipo = 'plano_governo'
              AND d.meta->>'sq_candidato' = %s
            ORDER BY c.ord
            LIMIT %s
            """,
            (str(sq_candidato), max(10, min(limite_chunks, 120))),
        ).fetchall()
        for r in rows:
            if r and r[0]:
                texts.append(str(r[0]))
    except Exception:
        return []
    return texts


def extrair_de_textos(textos: list[str]) -> dict[str, Any]:
    blob = _norm(" ".join(textos))
    temas: list[dict[str, Any]] = []
    keywords_por_eixo: dict[str, Counter[str]] = {}
    for label, eixo, kws in _LEXICO:
        hits = sum(blob.count(_norm(k)) for k in kws)
        if hits < 2:
            continue
        temas.append(
            {
                "nome": label,
                "query_news": ", ".join(kws[:5]),
                "eixo": eixo,
                "hits": hits,
            }
        )
        keywords_por_eixo.setdefault(eixo, Counter())
        for k in kws:
            if blob.count(_norm(k)):
                keywords_por_eixo[eixo][k] += blob.count(_norm(k))
    temas.sort(key=lambda t: -int(t["hits"]))
    eixos_kw = {
        e: ", ".join(k for k, _ in ctr.most_common(8))
        for e, ctr in keywords_por_eixo.items()
    }
    return {"temas": temas[:12], "keywords_eixos": eixos_kw, "chars": len(blob)}


def extrair_campanha(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    uf: str | None,
    sq_candidato: str | None,
    nm_candidato: str | None,
    adversarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Temas do plano do candidato do escopo (sq exato) + adversários com sq conhecido.

    `adversarios` deve trazer {"nome": ..., "sq_candidato": ...} — vem da nominata/base_redes,
    não de string solta. Adversário sem sq não gera tema (evita casar plano errado).
    """
    proprio: dict[str, Any] = {"temas": [], "keywords_eixos": {}, "chars": 0}
    if sq_candidato:
        textos = _textos_plano_por_sq(conn, sq_candidato=sq_candidato)
        if textos:
            proprio = extrair_de_textos(textos)

    adv_temas: list[dict[str, Any]] = []
    for adv in (adversarios or [])[:8]:
        sq_adv = adv.get("sq_candidato")
        nome_adv = (adv.get("nome") or "").strip()
        if not sq_adv or not nome_adv:
            continue
        t_adv = _textos_plano_por_sq(conn, sq_candidato=sq_adv, limite_chunks=30)
        if not t_adv:
            continue
        ex = extrair_de_textos(t_adv)
        for tm in ex.get("temas") or []:
            adv_temas.append(
                {
                    **tm,
                    "nome": f"{tm['nome']} (adversário: {nome_adv})",
                    "query_news": f"{nome_adv} {tm.get('query_news') or ''}".strip(),
                    "papel": "adversario",
                }
            )

    return {
        "temas_proprio": proprio.get("temas") or [],
        "temas_adversario": adv_temas[:8],
        "keywords_eixos": proprio.get("keywords_eixos") or {},
        "plano_chars": proprio.get("chars") or 0,
    }
