"""Capacidades OpenRouter / operacionais locais (não-cifra).

Tudo aqui é nivel=indicio ou artefato — nunca cifra TSE.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import httpx
import psycopg

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_IMG = "https://openrouter.ai/api/v1/chat/completions"


def _key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key.startswith("sk-or-"):
        raise RuntimeError("OPENROUTER_API_KEY indisponível para capacidades avançadas")
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"),
        "X-Title": "Apura Capacidades",
    }


def _model_web() -> str:
    return os.environ.get("APURA_WEB_MODEL") or "perplexity/sonar"


def _model_pdf() -> str:
    return os.environ.get("APURA_PDF_MODEL") or "mistralai/mistral-small"


def _model_vision() -> str:
    return os.environ.get("APURA_VISION_MODEL") or "openai/gpt-4o"


def _model_image() -> str:
    return os.environ.get("APURA_IMAGE_MODEL") or "google/gemini-2.0-flash-exp:free"


def _db_url() -> str | None:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("AGENTE_DATABASE_URL")
        or os.environ.get("POSTGRES_ADMIN_URL")
    )


async def pesquisar_web(params: dict[str, Any]) -> dict[str, Any]:
    q = (params.get("q") or params.get("query") or "").strip()
    if not q:
        return {"status": "vazio", "mensagem": "q obrigatório", "nivel": "indicio"}
    ctx = (params.get("contexto_campanha") or "")[:1500]
    user = q if not ctx else f"Contexto de campanha (não invente cifra):\n{ctx}\n\nPesquisa: {q}"
    body = {
        "model": _model_web(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Pesquise e resuma fontes. Marque tudo como indício. "
                    "Nunca invente resultado de urna ou cifra eleitoral oficial."
                ),
            },
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"pesquisa web indisponível ({r.status_code})",
            "nivel": "indicio",
            "nota_metodologica": (r.text or "")[:400],
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    if not text.strip():
        return {"status": "vazio", "mensagem": "sem resultados na janela", "nivel": "indicio"}
    return {
        "status": "ok",
        "nivel": "indicio",
        "itens": [{"titulo": "Síntese web", "resumo": text[:8000], "fonte": _model_web()}],
        "nota_metodologica": "Indício via Perplexity/OpenRouter — não é cifra TSE.",
    }


async def ler_pdf(params: dict[str, Any]) -> dict[str, Any]:
    url = (params.get("url") or "").strip()
    texto = (params.get("texto") or "").strip()
    pergunta = (params.get("pergunta") or "Resuma os pontos relevantes para a campanha.").strip()
    if not url and not texto:
        return {"status": "vazio", "mensagem": "informe url ou texto do PDF", "nivel": "indicio"}
    content: Any
    if url:
        content = [
            {"type": "text", "text": pergunta},
            {"type": "text", "text": f"Documento em URL: {url}. Extraia e responda com base nele."},
        ]
        # Alguns modelos aceitam file URL; enviamos instrução + fetch texto curto se possível
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                fr = await client.get(url)
            if fr.status_code < 400 and "text" in (fr.headers.get("content-type") or ""):
                content.append({"type": "text", "text": fr.text[:50000]})
            elif fr.status_code < 400:
                content.append(
                    {
                        "type": "text",
                        "text": (
                            f"(binário {fr.headers.get('content-type')}; "
                            f"{len(fr.content)} bytes — peça ao usuário colar trechos se o modelo não ler)"
                        ),
                    }
                )
        except Exception as exc:
            return {
                "status": "vazio",
                "mensagem": f"não foi possível baixar o PDF: {exc}",
                "nivel": "indicio",
            }
    else:
        content = f"{pergunta}\n\n---\n{texto[:50000]}"
    body = {
        "model": _model_pdf(),
        "messages": [
            {
                "role": "system",
                "content": "Leia o documento. Indício apenas. Sem inventar cifras de urna.",
            },
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"leitura PDF indisponível ({r.status_code})",
            "nivel": "indicio",
            "nota_metodologica": (r.text or "")[:400],
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {
        "status": "ok" if text.strip() else "vazio",
        "nivel": "indicio",
        "itens": [{"resumo": text[:12000], "fonte": "pdf"}],
        "mensagem": None if text.strip() else "sem conteúdo extraído",
        "nota_metodologica": "Indício de documento — cruzar com oficial se for cifra.",
    }


async def ler_imagem(params: dict[str, Any]) -> dict[str, Any]:
    url = (params.get("url") or params.get("image_url") or "").strip()
    pergunta = (params.get("pergunta") or "Descreva o que é relevante para a campanha.").strip()
    if not url:
        return {"status": "vazio", "mensagem": "url da imagem obrigatória", "nivel": "indicio"}
    body = {
        "model": _model_vision(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": pergunta},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"visão indisponível ({r.status_code})",
            "nivel": "indicio",
            "nota_metodologica": (r.text or "")[:400],
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {
        "status": "ok" if text.strip() else "vazio",
        "nivel": "indicio",
        "itens": [{"resumo": text[:8000], "fonte": "imagem"}],
        "nota_metodologica": "Leitura visual = indício.",
    }


async def transcrever_audio(params: dict[str, Any]) -> dict[str, Any]:
    url = (params.get("url") or "").strip()
    if not url:
        return {"status": "vazio", "mensagem": "url do áudio obrigatória", "nivel": "indicio"}
    # OpenRouter não unifica whisper; tentamos modelo multimodal com URL
    body = {
        "model": os.environ.get("APURA_AUDIO_MODEL") or "openai/gpt-4o-audio-preview",
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Transcreva o áudio em {url} (português BR se possível) e resuma "
                    "pontos úteis para campanha. Se não conseguir ouvir, diga lacuna."
                ),
            }
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": (
                "transcrição indisponível neste ambiente — envie o texto do áudio "
                f"ou configure APURA_AUDIO_MODEL ({r.status_code})"
            ),
            "nivel": "indicio",
            "nota_metodologica": (r.text or "")[:400],
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {
        "status": "ok" if text.strip() else "vazio",
        "nivel": "indicio",
        "itens": [{"resumo": text[:8000], "fonte": "audio"}],
        "nota_metodologica": "Áudio = indício.",
    }


async def gerar_imagem(params: dict[str, Any]) -> dict[str, Any]:
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        return {"status": "vazio", "mensagem": "prompt obrigatório", "nivel": "artefato"}
    ctx = (params.get("contexto_campanha") or "")[:800]
    full = prompt if not ctx else f"{prompt}\n\nContexto campanha: {ctx}"
    body = {
        "model": _model_image(),
        "messages": [
            {
                "role": "user",
                "content": (
                    "Gere uma descrição detalhada de imagem de campanha (storyboard) "
                    "pronta para produção, e se o modelo suportar URL de imagem, inclua. "
                    f"Pedido: {full}"
                ),
            }
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_OPENROUTER_IMG, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"geração de imagem indisponível ({r.status_code})",
            "nivel": "artefato",
            "nota_metodologica": (r.text or "")[:400],
        }
    msg = (r.json().get("choices") or [{}])[0].get("message", {}) or {}
    text = msg.get("content") or ""
    return {
        "status": "ok" if text.strip() else "vazio",
        "nivel": "artefato",
        "itens": [{"descricao": text[:8000]}],
        "nota_metodologica": "Artefato gerado — não é dado oficial.",
    }


async def gerar_mapa_html(params: dict[str, Any]) -> dict[str, Any]:
    titulo = (params.get("titulo") or "Mapa estratégico").strip()[:120]
    eixos = (params.get("eixos") or params.get("conteudo") or "").strip()
    if not eixos:
        return {"status": "vazio", "mensagem": "informe eixos/conteudo do mapa", "nivel": "artefato"}
    ctx = (params.get("contexto_campanha") or "")[:1500]
    body = {
        "model": os.environ.get("APURA_WRITER_MODEL") or "openai/gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Gere um único documento HTML5 autocontido (CSS inline) com um mapa "
                    "estratégico visual de campanha: blocos, setas em CSS, legendas. "
                    "Sem scripts externos. Sem inventar cifras — use só o que o usuário passou."
                ),
            },
            {
                "role": "user",
                "content": f"Título: {titulo}\nContexto:\n{ctx}\n\nEixos:\n{eixos[:6000]}",
            },
        ],
        "temperature": 0.4,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"mapa HTML indisponível ({r.status_code})",
            "nivel": "artefato",
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    m = re.search(r"<html[\s\S]*</html>", text, re.I)
    html = m.group(0) if m else text
    if not html.strip():
        return {"status": "vazio", "mensagem": "modelo não retornou HTML", "nivel": "artefato"}
    return {
        "status": "ok",
        "nivel": "artefato",
        "html": html[:100000],
        "titulo": titulo,
        "nota_metodologica": "Mapa estratégico gerado — artefato, não urna.",
    }


def operacional_contato(params: dict[str, Any], *, campanha_id: str | None = None) -> dict[str, Any]:
    acao = (params.get("acao") or "listar").strip().lower()
    url = _db_url()
    if not url or not campanha_id:
        return {
            "status": "vazio",
            "mensagem": "campanha/banco indisponível para contatos",
            "nivel": "operacional",
        }
    with psycopg.connect(url) as conn:
        if acao == "salvar":
            nome = (params.get("nome") or "").strip()
            if not nome:
                return {"status": "vazio", "mensagem": "nome obrigatório", "nivel": "operacional"}
            cid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO ctl.campanha_contato
                  (id, campanha_id, nome, papel, telefone, email, notas)
                VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s)
                """,
                (
                    cid,
                    campanha_id,
                    nome[:200],
                    (params.get("papel") or "")[:120] or None,
                    (params.get("telefone") or "")[:60] or None,
                    (params.get("email") or "")[:200] or None,
                    (params.get("notas") or "")[:2000] or None,
                ),
            )
            conn.commit()
            return {
                "status": "ok",
                "nivel": "operacional",
                "itens": [{"id": cid, "nome": nome, "acao": "salvo"}],
            }
        q = (params.get("q") or params.get("nome") or "").strip()
        rows = conn.execute(
            """
            SELECT id::text, nome, papel, telefone, email, notas
            FROM ctl.campanha_contato
            WHERE campanha_id = %s::uuid
              AND (%s = '' OR nome ILIKE '%%' || %s || '%%' OR papel ILIKE '%%' || %s || '%%')
            ORDER BY nome
            LIMIT 30
            """,
            (campanha_id, q, q, q),
        ).fetchall()
    itens = [
        {
            "id": r[0],
            "nome": r[1],
            "papel": r[2],
            "telefone": r[3],
            "email": r[4],
            "notas": r[5],
        }
        for r in rows
    ]
    return {
        "status": "ok" if itens else "vazio",
        "nivel": "operacional",
        "itens": itens,
        "mensagem": None if itens else "nenhum contato cadastrado neste recorte",
    }


def operacional_tarefa(params: dict[str, Any], *, campanha_id: str | None = None, usuario_id: str | None = None) -> dict[str, Any]:
    acao = (params.get("acao") or "listar").strip().lower()
    url = _db_url()
    if not url or not campanha_id:
        return {
            "status": "vazio",
            "mensagem": "campanha/banco indisponível para tarefas",
            "nivel": "operacional",
        }
    with psycopg.connect(url) as conn:
        if acao in ("criar", "gravar", "salvar"):
            titulo = (params.get("titulo") or params.get("texto") or "").strip()
            if not titulo:
                return {"status": "vazio", "mensagem": "titulo/texto obrigatório", "nivel": "operacional"}
            tid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO ctl.campanha_tarefa
                  (id, campanha_id, titulo, descricao, status, criado_por)
                VALUES (%s::uuid, %s::uuid, %s, %s, 'aberta', %s::uuid)
                """,
                (
                    tid,
                    campanha_id,
                    titulo[:300],
                    (params.get("descricao") or "")[:4000] or None,
                    usuario_id,
                ),
            )
            conn.commit()
            return {
                "status": "ok",
                "nivel": "operacional",
                "itens": [{"id": tid, "titulo": titulo, "status": "aberta"}],
            }
        if acao == "concluir":
            tid = (params.get("id") or "").strip()
            if not tid:
                return {"status": "vazio", "mensagem": "id da tarefa obrigatório", "nivel": "operacional"}
            conn.execute(
                """
                UPDATE ctl.campanha_tarefa
                SET status = 'concluida', atualizado_em = now()
                WHERE id = %s::uuid AND campanha_id = %s::uuid
                """,
                (tid, campanha_id),
            )
            conn.commit()
            return {"status": "ok", "nivel": "operacional", "itens": [{"id": tid, "status": "concluida"}]}
        rows = conn.execute(
            """
            SELECT id::text, titulo, descricao, status, criado_em::text
            FROM ctl.campanha_tarefa
            WHERE campanha_id = %s::uuid
              AND (
                COALESCE(%s, '') = ''
                OR status = %s
              )
            ORDER BY criado_em DESC
            LIMIT 40
            """,
            (
                campanha_id,
                (params.get("status") or "").strip() or None,
                (params.get("status") or "").strip() or None,
            ),
        ).fetchall()
    itens = [
        {"id": r[0], "titulo": r[1], "descricao": r[2], "status": r[3], "criado_em": r[4]}
        for r in rows
    ]
    return {
        "status": "ok" if itens else "vazio",
        "nivel": "operacional",
        "itens": itens,
        "mensagem": None if itens else "nenhuma tarefa neste filtro",
    }


LOCAL_METHODS = frozenset(
    {
        "pesquisar_web",
        "ler_pdf",
        "ler_imagem",
        "transcrever_audio",
        "gerar_imagem",
        "gerar_mapa_html",
        "operacional_contato",
        "operacional_tarefa",
    }
)


async def executar_local(
    method: str,
    params: dict[str, Any],
    *,
    campanha_id: str | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    p = dict(params or {})
    if method == "pesquisar_web":
        return await pesquisar_web(p)
    if method == "ler_pdf":
        return await ler_pdf(p)
    if method == "ler_imagem":
        return await ler_imagem(p)
    if method == "transcrever_audio":
        return await transcrever_audio(p)
    if method == "gerar_imagem":
        return await gerar_imagem(p)
    if method == "gerar_mapa_html":
        return await gerar_mapa_html(p)
    if method == "operacional_contato":
        return operacional_contato(p, campanha_id=campanha_id)
    if method == "operacional_tarefa":
        return operacional_tarefa(p, campanha_id=campanha_id, usuario_id=usuario_id)
    return {"erro": f"método local desconhecido: {method}"}
