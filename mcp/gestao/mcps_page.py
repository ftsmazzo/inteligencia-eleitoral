"""Página MCPs da campanha — texto para a equipe, sem jargão."""
from __future__ import annotations

import os
from typing import Any

import psycopg

from gestao import store

_HOST = (
    os.environ.get("APURA_SITE_URL")
    or "https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host"
).rstrip("/")


def _base() -> str:
    return _HOST


def pacotes_legiveis(campanha_nome: str, status: dict[str, Any]) -> list[dict[str, Any]]:
    candidato = status.get("nm_urna") or status.get("nm_candidato") or "o candidato da campanha"
    uf = status.get("sg_uf") or "—"
    cargo = status.get("cargo_label") or "—"
    ano = status.get("ano_ref") or 2026
    slug = (campanha_nome or "campanha").strip() or "campanha"

    return [
        {
            "id": "fato",
            "nome": "MCP Fato",
            "para_que": "Números oficiais do Brasil",
            "url": f"{_base()}/mcp",
            "servidor": "inteligencia-eleitoral-brasil",
            "cifra": True,
            "em_uma_frase": "É a fonte dos números: urna, contas, população e Câmara.",
            "entrega": [
                "Votos e quem foi eleito (por município, UF ou Brasil)",
                "Quem concorreu e dados do candidato no TSE",
                "Receitas e despesas de campanha",
                "Perfil do eleitorado, comparecimento, coligações",
                "População (IBGE), CadÚnico e Bolsa Família",
                "Deputados, proposições e votos na Câmara",
                "Planos de governo em geral (acervo nacional)",
                "Notícias e Instagram — sempre como indício, nunca como cifra",
            ],
            "nao_entrega": [
                "Não inventa resultado de 2026 antes da urna",
                "Não estima o que a base não tem",
            ],
            "quando_usar": "Quando a equipe ou a IA precisar de número confiável.",
        },
        {
            "id": "rag",
            "nome": "MCP RAG · Campanha",
            "para_que": f"Textos e planos de {candidato} ({cargo}, {uf}, {ano})",
            "url": f"{_base()}/mcp/rag",
            "servidor": f"ie-rag-{slug}",
            "cifra": False,
            "em_uma_frase": "Busca o que está escrito nos planos e fichas desta campanha.",
            "entrega": [
                "Trechos do plano de governo sobre um tema (saúde, segurança…)",
                "Comparação de promessas entre anos (ex.: 2022 vs 2026)",
                "Fichas e notas indexadas da campanha",
            ],
            "nao_entrega": [
                "Número no texto do plano não vira fato de urna",
                "Não substitui votação ou eleitos",
            ],
            "quando_usar": "Quando perguntarem “o que o plano diz sobre…” ou narrativa de programa.",
        },
        {
            "id": "contexto",
            "nome": "MCP Contexto · Campanha",
            "para_que": f"Identidade e memória da campanha {slug}",
            "url": f"{_base()}/mcp/contexto",
            "servidor": f"ie-contexto-{slug}",
            "cifra": False,
            "em_uma_frase": "Diz quem é o candidato desta conta e o que a equipe já indexou.",
            "entrega": [
                "Nome, cargo, UF, ano e partido do candidato monitorado",
                "Memória da campanha (trajetória, concorrentes, dossiê, redes)",
                "Temas principais extraídos do plano",
                "Configuração do Radar (alvos e eixos)",
            ],
            "nao_entrega": [
                "Não é resultado de urna",
                "Memória é contexto — só vira cifra se vier do MCP Fato",
            ],
            "quando_usar": "Para a IA saber o escopo sem perguntar de novo “quem é o nosso candidato?”.",
        },
    ]


def montar_pagina(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    usuario_id: str,
    email: str,
    mcp_token: str,
) -> dict[str, Any]:
    status = store.get_status(conn, campanha_id) or {}
    nome = status.get("campanha_nome") or "campanha"
    pacotes = pacotes_legiveis(nome, status)
    token = (mcp_token or "").strip()
    config_cursor = {
        "mcpServers": {
            p["servidor"]: {
                "url": p["url"],
                "headers": {"Authorization": f"Bearer {token or 'SEU_TOKEN_AQUI'}"},
            }
            for p in pacotes
        }
    }
    return {
        "status": "ok",
        "campanha": {
            "id": campanha_id,
            "nome": nome,
            "candidato": status.get("nm_urna") or status.get("nm_candidato"),
            "cargo": status.get("cargo_label"),
            "uf": status.get("sg_uf"),
            "ano_ref": status.get("ano_ref"),
            "partido": status.get("sg_partido"),
            "ambiente_status": status.get("ambiente_status"),
        },
        "usuario": {"email": email, "id": usuario_id},
        "token": token,
        "token_aviso": (
            "Este token é da sua conta nesta campanha. Use nos três MCPs. "
            "Não publique em rede social nem no git."
            if token
            else "Token MCP ainda não vinculado a esta conta — fale com o coordenador."
        ),
        "pacotes": pacotes,
        "como_conectar": {
            "cursor": "No Cursor: Settings → MCP → cole o JSON abaixo (já com o token).",
            "claude": "No Claude Desktop: mesmo JSON em claude_desktop_config.",
            "outra_ia": "Qualquer IA que aceite MCP HTTP: URL + Bearer token.",
        },
        "config_cursor": config_cursor,
        "mcp_externo": {
            "possivel": True,
            "resumo": (
                "Sim. Você pode conectar um MCP de outra aplicação (n8n, Postgres de outro "
                "produto, CRM, etc.) no mesmo Cursor ou Claude, ao lado destes três. "
                "Cada um tem a própria URL e o próprio token. A IA combina as fontes; "
                "o Apura não mistura sozinho o MCP externo com a urna."
            ),
            "como": [
                "Peça a URL HTTPS e o token do outro sistema",
                "Adicione mais uma entrada em mcpServers (nome livre)",
                "Mantenha os três MCPs desta campanha — não remova o Fato se precisar de número",
                "Lembre: cifra eleitoral só pelo MCP Fato desta plataforma",
            ],
        },
        "guia_url": f"{_base()}/guia",
    }
