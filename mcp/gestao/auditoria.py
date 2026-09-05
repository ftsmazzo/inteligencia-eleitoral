"""Auditoria de plataforma — interações, eventos e IA de boas práticas (só super).

Contrato §8 · P4. Cifras eleitorais NÃO entram aqui; só uso operacional.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
import psycopg

from gestao.plataforma import exigir_super, listar_eventos

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


def resumo_uso(
    conn: psycopg.Connection,
    *,
    dias: int = 7,
    campanha_id: str | None = None,
) -> dict[str, Any]:
    dias = max(1, min(int(dias), 90))
    params: list[Any] = [dias]
    filtro_camp = ""
    if campanha_id:
        filtro_camp = (
            "AND COALESCE(u.campanha_ativa_id, u.campanha_id) = %s::uuid"
        )
        params.append(campanha_id)

    usuarios = conn.execute(
        f"""
        SELECT u.id::text, u.email, u.nome,
               COALESCE(c.nome, '') AS campanha,
               u.quota_perguntas_used,
               u.quota_perguntas_max,
               (SELECT COUNT(*)::int FROM ctl.apura_mensagem m
                JOIN ctl.apura_sessao s ON s.id = m.sessao_id
                WHERE s.usuario_id = u.id AND m.papel = 'user'
                  AND m.criado_em >= now() - make_interval(days => %s)) AS perguntas_periodo,
               (SELECT MAX(m.criado_em) FROM ctl.apura_mensagem m
                JOIN ctl.apura_sessao s ON s.id = m.sessao_id
                WHERE s.usuario_id = u.id) AS ultima_msg
        FROM ctl.apura_usuario u
        LEFT JOIN ctl.campanha c ON c.id = COALESCE(u.campanha_ativa_id, u.campanha_id)
        WHERE u.ativo IS TRUE {filtro_camp}
        ORDER BY perguntas_periodo DESC, u.email
        LIMIT 200
        """,
        params,
    ).fetchall()

    por_usuario = [
        {
            "usuario_id": r[0],
            "email": r[1],
            "nome": r[2],
            "campanha_ativa": r[3],
            "quota_used": int(r[4] or 0),
            "quota_max": r[5],
            "perguntas_periodo": int(r[6] or 0),
            "ultima_msg": r[7].isoformat() if r[7] else None,
        }
        for r in usuarios
    ]

    tools_rows = conn.execute(
        """
        SELECT m.dados_json
        FROM ctl.apura_mensagem m
        WHERE m.papel = 'assistant'
          AND m.criado_em >= now() - make_interval(days => %s)
          AND m.dados_json IS NOT NULL
        ORDER BY m.criado_em DESC
        LIMIT 500
        """,
        (dias,),
    ).fetchall()

    tool_counts: dict[str, int] = {}
    perfil_counts: dict[str, int] = {}
    negadas = 0
    for (dj,) in tools_rows:
        data = dj if isinstance(dj, dict) else (json.loads(dj) if dj else {})
        pol = data.get("politica") or {}
        slug = pol.get("perfil_slug")
        if slug:
            perfil_counts[slug] = perfil_counts.get(slug, 0) + 1
        for tr in data.get("tool_results") or []:
            name = tr.get("tool") or "?"
            tool_counts[name] = tool_counts.get(name, 0) + 1
            res = tr.get("result") or {}
            if isinstance(res, dict) and res.get("erro") == "tool_negada_pelo_perfil":
                negadas += 1

    eventos_n = conn.execute(
        """
        SELECT COUNT(*)::int FROM ctl.evento_acesso
        WHERE ocorrido_em >= now() - make_interval(days => %s)
        """,
        (dias,),
    ).fetchone()

    campanhas = conn.execute(
        """
        SELECT c.id::text, c.nome, c.ambiente_status,
               (SELECT COUNT(*)::int FROM ctl.campanha_membro m
                WHERE m.campanha_id = c.id AND m.ativo IS TRUE),
               (SELECT COUNT(*)::int FROM ctl.apura_mensagem msg
                JOIN ctl.apura_sessao s ON s.id = msg.sessao_id
                JOIN ctl.apura_usuario u ON u.id = s.usuario_id
                WHERE COALESCE(u.campanha_ativa_id, u.campanha_id) = c.id
                  AND msg.papel = 'user'
                  AND msg.criado_em >= now() - make_interval(days => %s))
        FROM ctl.campanha c
        WHERE c.ativo IS TRUE
        ORDER BY c.nome
        """,
        (dias,),
    ).fetchall()

    return {
        "dias": dias,
        "campanha_id": campanha_id,
        "perguntas_total_periodo": sum(u["perguntas_periodo"] for u in por_usuario),
        "usuarios_ativos_periodo": sum(1 for u in por_usuario if u["perguntas_periodo"] > 0),
        "eventos_periodo": int(eventos_n[0] if eventos_n else 0),
        "tools_negadas": negadas,
        "tools_top": sorted(tool_counts.items(), key=lambda x: -x[1])[:15],
        "perfis_uso": sorted(perfil_counts.items(), key=lambda x: -x[1]),
        "por_usuario": por_usuario,
        "por_campanha": [
            {
                "campanha_id": r[0],
                "nome": r[1],
                "ambiente_status": r[2],
                "membros": int(r[3] or 0),
                "perguntas_periodo": int(r[4] or 0),
            }
            for r in campanhas
        ],
    }


def listar_interacoes(
    conn: psycopg.Connection,
    *,
    usuario_id: str | None = None,
    campanha_id: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    limite = max(1, min(int(limite), 200))
    clauses = ["m.papel IN ('user', 'assistant')"]
    params: list[Any] = []
    if usuario_id:
        clauses.append("s.usuario_id = %s::uuid")
        params.append(usuario_id)
    if campanha_id:
        clauses.append("COALESCE(u.campanha_ativa_id, u.campanha_id) = %s::uuid")
        params.append(campanha_id)
    params.append(limite)
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT m.id::text, m.papel, left(m.conteudo, 400), m.dados_json, m.criado_em,
               s.id::text, s.titulo, u.id::text, u.email, u.nome,
               c.id::text, c.nome
        FROM ctl.apura_mensagem m
        JOIN ctl.apura_sessao s ON s.id = m.sessao_id
        JOIN ctl.apura_usuario u ON u.id = s.usuario_id
        LEFT JOIN ctl.campanha c ON c.id = COALESCE(u.campanha_ativa_id, u.campanha_id)
        WHERE {where}
        ORDER BY m.criado_em DESC
        LIMIT %s
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        dj = r[3] if isinstance(r[3], dict) else (json.loads(r[3]) if r[3] else None)
        tools = []
        pol = None
        if isinstance(dj, dict):
            pol = dj.get("politica")
            tools = [
                {
                    "tool": t.get("tool"),
                    "erro": (t.get("result") or {}).get("erro")
                    if isinstance(t.get("result"), dict)
                    else None,
                }
                for t in (dj.get("tool_results") or [])
            ]
        out.append(
            {
                "mensagem_id": r[0],
                "papel": r[1],
                "trecho": r[2],
                "criado_em": r[4].isoformat() if r[4] else None,
                "sessao_id": r[5],
                "sessao_titulo": r[6],
                "usuario_id": r[7],
                "usuario_email": r[8],
                "usuario_nome": r[9],
                "campanha_id": r[10],
                "campanha_nome": r[11],
                "politica": pol,
                "tools": tools,
            }
        )
    return out


def _regras_heuristicas(resumo: dict[str, Any]) -> list[dict[str, str]]:
    """Sugestões determinísticas (sem LLM) a partir dos agregados."""
    tips: list[dict[str, str]] = []
    if resumo.get("tools_negadas", 0) > 0:
        tips.append(
            {
                "nivel": "atencao",
                "titulo": "Tools negadas pelo Perfil",
                "texto": (
                    f"{resumo['tools_negadas']} tentativas de tool fora do Perfil no período. "
                    "Revise se o Perfil do usuário está curto demais ou se há uso indevido."
                ),
            }
        )
    ociosos = [
        u
        for u in resumo.get("por_usuario") or []
        if u["perguntas_periodo"] == 0 and u.get("campanha_ativa")
    ]
    if len(ociosos) >= 3:
        tips.append(
            {
                "nivel": "info",
                "titulo": "Membros sem uso no período",
                "texto": (
                    f"{len(ociosos)} usuários com campanha e zero perguntas nos últimos "
                    f"{resumo.get('dias')} dias. Considere onboarding ou desativar vínculos."
                ),
            }
        )
    top = resumo.get("tools_top") or []
    if top and top[0][0] == "consultar_votacao" and top[0][1] > 20:
        tips.append(
            {
                "nivel": "dica",
                "titulo": "Uso intenso de votação",
                "texto": (
                    "Muitas chamadas a consultar_votacao. Oriente a equipe a fixar ano/cargo/UF "
                    "na pergunta para reduzir rodadas do orquestrador."
                ),
            }
        )
    camp_zeradas = [
        c
        for c in resumo.get("por_campanha") or []
        if c["membros"] > 0 and c["perguntas_periodo"] == 0
    ]
    if camp_zeradas:
        tips.append(
            {
                "nivel": "info",
                "titulo": "Campanhas sem chat no período",
                "texto": (
                    "Campanhas com membros e zero perguntas: "
                    + ", ".join(c["nome"] for c in camp_zeradas[:5])
                    + ("…" if len(camp_zeradas) > 5 else "")
                ),
            }
        )
    if not tips:
        tips.append(
            {
                "nivel": "ok",
                "titulo": "Uso estável",
                "texto": "Sem alertas operacionais fortes neste recorte. Continue monitorando tools negadas e cotas.",
            }
        )
    return tips


async def sugerir_boas_praticas(
    conn: psycopg.Connection,
    *,
    email_super: str,
    dias: int = 7,
    campanha_id: str | None = None,
    usar_llm: bool = True,
) -> dict[str, Any]:
    exigir_super(conn, email_super)
    resumo = resumo_uso(conn, dias=dias, campanha_id=campanha_id)
    heuristicas = _regras_heuristicas(resumo)
    eventos = listar_eventos(conn, campanha_id=campanha_id, limite=30)

    out: dict[str, Any] = {
        "resumo": {
            "dias": resumo["dias"],
            "perguntas_total_periodo": resumo["perguntas_total_periodo"],
            "usuarios_ativos_periodo": resumo["usuarios_ativos_periodo"],
            "eventos_periodo": resumo["eventos_periodo"],
            "tools_negadas": resumo["tools_negadas"],
            "tools_top": resumo["tools_top"],
            "perfis_uso": resumo["perfis_uso"],
        },
        "heuristicas": heuristicas,
        "llm": None,
        "aviso": (
            "Sugestões operacionais apenas. Não são cifras eleitorais; "
            "não substituem consulta Trilha A via tools."
        ),
    }

    if not usar_llm:
        return out

    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key.startswith("sk-or-"):
        out["llm"] = {"ok": False, "erro": "OPENROUTER_API_KEY indisponível — só heurísticas."}
        return out

    model = os.environ.get("APURA_GOVERNANCA_MODEL") or "openai/gpt-4o-mini"
    payload_ctx = {
        "resumo": out["resumo"],
        "heuristicas": heuristicas,
        "eventos_recentes": [
            {"acao": e["acao"], "quando": e["ocorrido_em"], "email": e.get("usuario_email")}
            for e in eventos[:20]
        ],
        "usuarios_top": (resumo.get("por_usuario") or [])[:12],
    }
    system = (
        "Você é auditor de uso da plataforma Apura (gestão de campanhas eleitorais). "
        "Comente APENAS padrões de uso: Perfis, tools, cotas, campanhas ociosas, boas práticas. "
        "PROIBIDO inventar ou estimar votos, percentuais eleitorais ou qualquer cifra TSE/IBGE. "
        "Se faltar dado operacional, diga a lacuna. Responda em português, 5–8 bullets curtos."
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                _OPENROUTER,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.environ.get(
                        "APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"
                    ),
                    "X-Title": "Apura Governanca",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": "Analise estes agregados:\n"
                            + json.dumps(payload_ctx, ensure_ascii=False, default=str)[:12000],
                        },
                    ],
                },
            )
        if r.status_code >= 400:
            out["llm"] = {"ok": False, "erro": r.text[:300], "modelo": model}
        else:
            text = r.json()["choices"][0]["message"].get("content") or ""
            out["llm"] = {"ok": True, "modelo": model, "texto": text}
    except Exception as exc:
        out["llm"] = {"ok": False, "erro": str(exc), "modelo": model}
    return out
