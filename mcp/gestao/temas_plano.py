"""Extrai temas e palavras-chave de planos de governo (acervo) e dossiê.

Nível indicio — heurística léxica, sem inventar cifra. Alimenta seed do Radar.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

import psycopg

from gestao import memoria

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

_STOP = {
    "para", "com", "por", "uma", "que", "dos", "das", "nao", "mais", "como",
    "este", "esta", "pelo", "pela", "ser", "seu", "sua", "tem", "foi", "sao",
}


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", (s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", t)


def _textos_plano(
    conn: psycopg.Connection,
    *,
    uf: str | None,
    sq_candidato: str | None,
    nm: str | None,
    limite_chunks: int = 60,
) -> list[str]:
    texts: list[str] = []
    try:
        params: list[Any] = []
        wheres = ["d.ativo IS TRUE", "d.tipo = 'plano_governo'"]
        if uf:
            wheres.append("d.sg_uf = %s")
            params.append(uf.upper())
        if sq_candidato:
            wheres.append("d.meta->>'sq_candidato' = %s")
            params.append(str(sq_candidato))
        elif nm:
            wheres.append("(d.nm_candidato ILIKE %s OR d.titulo ILIKE %s)")
            like = f"%{(nm or '').strip()[:40]}%"
            params.extend([like, like])
        else:
            return []
        params.append(max(10, min(limite_chunks, 120)))
        rows = conn.execute(
            f"""
            SELECT COALESCE(c.secao, '') || ' ' || left(COALESCE(c.texto, ''), 2500)
            FROM acervo.documento d
            JOIN acervo.chunk c ON c.documento_id = d.id
            WHERE {' AND '.join(wheres)}
            ORDER BY c.ord
            LIMIT %s
            """,
            params,
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


def extrair_dossie(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    blocos = memoria.listar(conn, campanha_id, limite=40)
    for b in blocos:
        tipo = (b.get("tipo") or "")
        if not (tipo.startswith("dossie") or tipo in ("perfil_eleitor", "base_trajetoria")):
            continue
        titulo = (b.get("titulo") or "").strip()
        if len(titulo) < 4 or titulo.lower().startswith("dossiê parte"):
            continue
        corpo = _norm(b.get("corpo") or "")
        # títulos curtos de seção viram tema; corpo gera query
        tokens = [t for t in re.findall(r"[a-z]{4,}", corpo) if t not in _STOP][:6]
        out.append(
            {
                "nome": titulo[:80],
                "query_news": ", ".join(tokens) if tokens else titulo,
                "fonte": tipo,
            }
        )
    return out[:10]


def extrair_campanha(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    uf: str | None,
    sq_candidato: str | None,
    nm_candidato: str | None,
    adversarios: list[str] | None = None,
) -> dict[str, Any]:
    """Combina plano do candidato + adversários + títulos do dossiê."""
    textos = _textos_plano(conn, uf=uf, sq_candidato=sq_candidato, nm=nm_candidato)
    proprio = extrair_de_textos(textos) if textos else {"temas": [], "keywords_eixos": {}, "chars": 0}
    adv_temas: list[dict[str, Any]] = []
    for adv in (adversarios or [])[:6]:
        t_adv = _textos_plano(conn, uf=uf, sq_candidato=None, nm=adv, limite_chunks=30)
        if not t_adv:
            continue
        ex = extrair_de_textos(t_adv)
        for tm in ex.get("temas") or []:
            adv_temas.append(
                {
                    **tm,
                    "nome": f"{tm['nome']} ({adv})",
                    "query_news": f"{adv} {tm.get('query_news') or ''}".strip(),
                    "papel": "adversario",
                }
            )
    dossie = extrair_dossie(conn, campanha_id)
    return {
        "temas_proprio": proprio.get("temas") or [],
        "temas_adversario": adv_temas[:8],
        "temas_dossie": dossie,
        "keywords_eixos": proprio.get("keywords_eixos") or {},
        "plano_chars": proprio.get("chars") or 0,
    }
