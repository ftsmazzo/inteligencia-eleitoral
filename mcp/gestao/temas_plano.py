"""Extrai temas e palavras-chave do plano de governo (acervo) por sq_candidato exato.

Nível indício — heurística léxica sobre texto oficial do plano. Nunca casa por ILIKE
solto no acervo inteiro (evita colar tema do adversário errado em quem quer que seja).
Quando o sq_candidato não é conhecido (comum p/ adversários vindos só do nome, sem
redes), tenta um fallback estrito: mesmo pleito (uf + cargo + ano_eleicao) + nome mais
parecido entre os poucos candidatos daquele pleito — nunca cruza pleitos diferentes.
Sem nenhum match, não gera tema — ausência é inexistente, não zero.
"""
from __future__ import annotations

import difflib
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


def _candidatos_do_pleito(
    conn: psycopg.Connection,
    *,
    uf: str | None,
    cargo: str | None,
    ano_eleicao: int | None,
) -> list[tuple[str, str]]:
    """Lista (sq_candidato, nm_candidato) dos planos de governo do mesmo pleito."""
    if not uf or not cargo:
        return []
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT d.meta->>'sq_candidato', COALESCE(d.nm_candidato, '')
            FROM acervo.documento d
            WHERE d.ativo IS TRUE AND d.tipo = 'plano_governo'
              AND lower(d.cargo) = lower(%s) AND upper(d.sg_uf) = upper(%s)
              AND (%s::int IS NULL OR d.ano_eleicao = %s::int)
              AND d.meta->>'sq_candidato' IS NOT NULL
            """,
            (cargo, uf, ano_eleicao, ano_eleicao),
        ).fetchall()
    except Exception:
        return []
    return [(str(r[0]), r[1] or "") for r in rows if r[0]]


def _sq_por_nome_no_pleito(
    conn: psycopg.Connection,
    *,
    nome: str | None,
    uf: str | None,
    cargo: str | None,
    ano_eleicao: int | None,
    excluir_sq: set[str] | None = None,
    limiar: float = 0.72,
) -> tuple[str | None, float, list[dict[str, Any]]]:
    """Fallback sem sq: acha o candidato mais parecido por nome DENTRO do mesmo
    pleito (uf+cargo+ano) — nunca cruza pleitos. Tolerante a texto corrompido
    (encoding ruim no PDF/nome) porque compara só letras a-z após normalizar."""
    alvo = re.sub(r"[^a-z]", "", _norm(nome or ""))
    if not alvo:
        return None, 0.0, []
    excluir = {str(s) for s in (excluir_sq or set())}
    candidatos = _candidatos_do_pleito(conn, uf=uf, cargo=cargo, ano_eleicao=ano_eleicao)
    melhor_sq, melhor_score = None, 0.0
    debug: list[dict[str, Any]] = []
    for sq, nm in candidatos:
        if sq in excluir:
            continue
        cand = re.sub(r"[^a-z]", "", _norm(nm))
        if not cand:
            continue
        score = difflib.SequenceMatcher(None, alvo, cand).ratio()
        debug.append({"sq": sq, "nome": nm, "score": round(score, 2)})
        if score > melhor_score:
            melhor_score, melhor_sq = score, sq
    debug.sort(key=lambda d: -d["score"])
    if melhor_sq and melhor_score >= limiar:
        return melhor_sq, melhor_score, debug[:6]
    return None, melhor_score, debug[:6]


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
    cargo: str | None = None,
    ano_eleicao: int | None = 2026,
) -> dict[str, Any]:
    """Temas do plano do candidato do escopo + adversários.

    Casa por sq_candidato exato quando disponível. Quando falta (ou o sq exato não
    tem texto no acervo), tenta um fallback restrito ao MESMO pleito (uf+cargo+ano):
    nome mais parecido entre os poucos candidatos daquele pleito — nunca cruza
    pleitos/UFs/cargos diferentes. `adversarios` deve trazer {"nome":..., "sq_candidato":...}
    vindo da nominata/base_redes (pode vir sem sq — o fallback tenta achar por nome).
    """
    diag: dict[str, Any] = {"proprio": {}, "adversarios": []}
    todos_sq_conhecidos = {str(sq_candidato)} if sq_candidato else set()
    for a in adversarios or []:
        if a.get("sq_candidato"):
            todos_sq_conhecidos.add(str(a["sq_candidato"]))

    proprio: dict[str, Any] = {"temas": [], "keywords_eixos": {}, "chars": 0}
    sq_proprio_usado = str(sq_candidato) if sq_candidato else None
    textos = _textos_plano_por_sq(conn, sq_candidato=sq_proprio_usado) if sq_proprio_usado else []
    if not textos:
        sq_fb, score, cands = _sq_por_nome_no_pleito(
            conn,
            nome=nm_candidato,
            uf=uf,
            cargo=cargo,
            ano_eleicao=ano_eleicao,
            excluir_sq=todos_sq_conhecidos - ({sq_proprio_usado} if sq_proprio_usado else set()),
        )
        diag["proprio"] = {"sq_tentado": sq_proprio_usado, "sq_fallback": sq_fb, "score": round(score, 2), "candidatos": cands}
        if sq_fb:
            textos = _textos_plano_por_sq(conn, sq_candidato=sq_fb)
            sq_proprio_usado = sq_fb
            todos_sq_conhecidos.add(sq_fb)
    else:
        diag["proprio"] = {"sq_tentado": sq_proprio_usado, "sq_fallback": None, "score": 1.0, "candidatos": []}
    if textos:
        proprio = extrair_de_textos(textos)

    adv_temas: list[dict[str, Any]] = []
    for adv in (adversarios or [])[:8]:
        sq_adv = adv.get("sq_candidato")
        nome_adv = (adv.get("nome") or "").strip()
        if not nome_adv:
            continue
        sq_adv_usado = str(sq_adv) if sq_adv else None
        t_adv = _textos_plano_por_sq(conn, sq_candidato=sq_adv_usado, limite_chunks=30) if sq_adv_usado else []
        if not t_adv:
            sq_fb, score, cands = _sq_por_nome_no_pleito(
                conn,
                nome=nome_adv,
                uf=uf,
                cargo=cargo,
                ano_eleicao=ano_eleicao,
                excluir_sq=todos_sq_conhecidos - ({sq_adv_usado} if sq_adv_usado else set()),
            )
            diag["adversarios"].append({"nome": nome_adv, "sq_tentado": sq_adv_usado, "sq_fallback": sq_fb, "score": round(score, 2)})
            if sq_fb:
                t_adv = _textos_plano_por_sq(conn, sq_candidato=sq_fb, limite_chunks=30)
                todos_sq_conhecidos.add(sq_fb)
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
        "sq_proprio_usado": sq_proprio_usado,
        "diag": diag,
    }
