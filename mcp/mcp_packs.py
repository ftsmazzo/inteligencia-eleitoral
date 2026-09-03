"""Três servidores MCP lógicos no mesmo host.

- fato (/mcp): Trilha A + clima + acervo nacional (compatível com o Apura)
- rag (/mcp/rag): Trilha B travada na campanha governador-amapa (AP, 2026)
- contexto (/mcp/contexto): escopo, memória e temas dessa campanha

Cifra nunca sai do RAG nem do Contexto. Número só nas tools de fato.
"""
from __future__ import annotations

import os
from typing import Any

import psycopg

SLUG_AMAPA = os.environ.get("MCP_CAMPANHA_SLUG", "governador-amapa")

TOOLS_FATO = (
    "catalogo",
    "municipio",
    "nominata",
    "votacao",
    "comparecimento",
    "eleitorado",
    "coligacao",
    "vagas",
    "bem",
    "rede_social",
    "complementar",
    "receita",
    "despesa",
    "contas_resumo",
    "eleitos",
    "populacao",
    "cadunico",
    "bolsa_familia",
    "deputados_casa",
    "senadores",
    "proposicoes",
    "votos_camara",
    "depara_parlamentar",
    "acervo",
    "acervo_comparar",
    "linha_temporal",
    "cruzamento_social",
    "mandato_urna",
    "clima",
)

TOOLS_RAG = ("catalogo", "acervo", "acervo_comparar")
TOOLS_CONTEXTO = ("catalogo", "escopo", "memoria", "temas_plano", "radar")

PACKS: dict[str, frozenset[str]] = {
    "fato": frozenset(TOOLS_FATO),
    "rag": frozenset(TOOLS_RAG),
    "contexto": frozenset(TOOLS_CONTEXTO),
}

_HOST = "https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host"

META = {
    "fato": {
        "servidor": "inteligencia-eleitoral-brasil",
        "url": f"{_HOST}/mcp",
        "trilha": "A · Fato (urna, contas, social, Câmara) + acervo nacional + clima",
        "cifra": True,
        "campanha": None,
        "tools": list(TOOLS_FATO),
    },
    "rag": {
        "servidor": "ie-rag-amapa",
        "url": f"{_HOST}/mcp/rag",
        "trilha": "B · Acervo (planos/fichas) da campanha governador Amapá 2026",
        "cifra": False,
        "campanha": SLUG_AMAPA,
        "aviso": "Cifra no texto do plano é pista, não fato. Número só no MCP /mcp.",
        "tools": list(TOOLS_RAG),
    },
    "contexto": {
        "servidor": "ie-contexto-amapa",
        "url": f"{_HOST}/mcp/contexto",
        "trilha": "Contexto operacional da campanha (escopo, memória, temas, radar)",
        "cifra": False,
        "campanha": SLUG_AMAPA,
        "aviso": "Identidade e memória da campanha. Não substitui votacao/eleitos.",
        "tools": list(TOOLS_CONTEXTO),
    },
}


def meta_publica(pack: str) -> dict[str, Any]:
    m = dict(META[pack])
    m["protocolo"] = "POST JSON {method, params}"
    m["auth"] = "Authorization: Bearer <TOKEN> ou X-Token"
    return m


def catalogo_pack(pack: str) -> dict[str, Any]:
    m = meta_publica(pack)
    notas = {
        "catalogo": "Este pacote (não o catálogo nacional completo)",
        "acervo": "Busca semântica no acervo; UF/ano travados na campanha Amapá",
        "acervo_comparar": "Mesmo tema em dois anos; candidato default da campanha",
        "escopo": "Candidato, cargo, UF, ano e sq_candidato da campanha",
        "memoria": "Blocos indexados (dossiê, trajetória, redes). nivel=indicio salvo fato explícito",
        "temas_plano": "Temas extraídos do plano de governo (indício léxico)",
        "radar": "Config do Radar (nome, UF, cargo) — não é feed de notícia",
    }
    return {
        "status": "ok",
        "pacote": pack,
        "servidor": m["servidor"],
        "cifra": m["cifra"],
        "campanha": m.get("campanha"),
        "aviso": m.get("aviso") or m["trilha"],
        "pacotes": [{"pacote": t, "nota": notas.get(t, t)} for t in m["tools"]],
    }


def resolver_campanha_amapa(conn: psycopg.Connection) -> dict[str, Any] | None:
    from gestao import store

    row = conn.execute(
        """
        SELECT id::text FROM ctl.campanha
        WHERE nome = %s AND ativo IS TRUE
        """,
        (SLUG_AMAPA,),
    ).fetchone()
    if not row or not row[0]:
        return None
    status = store.get_status(conn, row[0])
    return status or None


def campanha_ausente() -> dict[str, Any]:
    return {
        "status": "vazio",
        "nivel": "indicio",
        "campanha": SLUG_AMAPA,
        "aviso": "Campanha governador-amapa inexistente neste banco.",
    }


def filtrar_rag(params: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    p = dict(params or {})
    p["uf"] = (status.get("sg_uf") or "AP").upper()
    if p.get("ano_eleicao") is None:
        p["ano_eleicao"] = int(status.get("ano_ref") or 2026)
    if not (p.get("nm_candidato") or "").strip():
        p["nm_candidato"] = status.get("nm_urna") or status.get("nm_candidato")
    return p


def montar_escopo(conn: psycopg.Connection) -> dict[str, Any]:
    from gestao import memoria
    from radar import store as radar_store

    status = resolver_campanha_amapa(conn)
    if not status:
        return campanha_ausente()
    radar_cfg = radar_store.get_config(conn, status["campanha_id"])
    return {
        "status": "ok",
        "nivel": "referencia",
        "campanha": SLUG_AMAPA,
        "escopo": {
            "candidato": status.get("nm_urna") or status.get("nm_candidato"),
            "nome": status.get("nm_candidato"),
            "partido": status.get("sg_partido"),
            "cargo": status.get("cargo_label"),
            "cd_cargo": status.get("cd_cargo"),
            "uf": status.get("sg_uf"),
            "ano_ref": status.get("ano_ref"),
            "sq_candidato": status.get("sq_candidato"),
            "nr_candidato": status.get("nr_candidato"),
            "ambiente_status": status.get("ambiente_status"),
        },
        "radar": radar_cfg,
        "texto": memoria.texto_escopo_para_apura(status, radar_cfg),
        "aviso": "Identidade da campanha. Cifra de urna só no MCP /mcp (votacao, eleitos, …).",
    }


def montar_memoria(
    conn: psycopg.Connection,
    *,
    query: str | None = None,
    tipo: str | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    from gestao import memoria

    status = resolver_campanha_amapa(conn)
    if not status:
        return campanha_ausente()
    linhas = memoria.listar(
        conn,
        status["campanha_id"],
        tipo=(tipo or None),
        query=(query or None),
        limite=limite,
    )
    return {
        "status": "ok" if linhas else "vazio",
        "nivel": "indicio",
        "campanha": SLUG_AMAPA,
        "linhas": linhas,
        "aviso": "Memória da campanha. Não use como cifra de urna.",
    }


def montar_temas(conn: psycopg.Connection) -> dict[str, Any]:
    from gestao import temas_plano

    status = resolver_campanha_amapa(conn)
    if not status:
        return campanha_ausente()
    cargo_key = None
    from gestao.store import CARGOS

    for c in CARGOS:
        if c["cd_cargo"] == status.get("cd_cargo"):
            cargo_key = c["key"]
            break
    dados = temas_plano.extrair_campanha(
        conn,
        campanha_id=status["campanha_id"],
        uf=status.get("sg_uf"),
        sq_candidato=str(status["sq_candidato"]) if status.get("sq_candidato") else None,
        nm_candidato=status.get("nm_urna") or status.get("nm_candidato"),
        cargo=cargo_key or "governador",
        ano_eleicao=int(status.get("ano_ref") or 2026),
    )
    return {
        "status": "ok" if (dados.get("temas_proprio") or dados.get("plano_chars")) else "vazio",
        "nivel": "indicio",
        "campanha": SLUG_AMAPA,
        **dados,
        "aviso": "Temas extraídos do plano (heurística). Não é resultado de urna.",
    }


def montar_radar(conn: psycopg.Connection) -> dict[str, Any]:
    from radar import store as radar_store

    status = resolver_campanha_amapa(conn)
    if not status:
        return campanha_ausente()
    cfg = radar_store.get_config(conn, status["campanha_id"])
    return {
        "status": "ok" if (cfg.get("candidato_nome") or cfg.get("uf")) else "vazio",
        "nivel": "indicio",
        "campanha": SLUG_AMAPA,
        "config": cfg,
        "aviso": "Configuração do Radar, não o feed. Clima em tempo real: tool clima no MCP /mcp.",
    }
