"""Capacidades OpenRouter / operacionais locais (não-cifra).

Tudo aqui é nivel=indicio ou artefato — nunca cifra TSE.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid
from typing import Any

import httpx
import psycopg

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_IMAGES = "https://openrouter.ai/api/v1/images"
_MAX_B64 = 5_500_000  # ~4 MB arquivo


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
    from apura import modelos as catalogo_modelos

    return catalogo_modelos.modelo_web()


def _model_pdf() -> str:
    from apura import modelos as catalogo_modelos

    return catalogo_modelos.modelo_pdf()


def _model_vision() -> str:
    from apura import modelos as catalogo_modelos

    return catalogo_modelos.modelo_visao()


def _model_image() -> str:
    from apura import modelos as catalogo_modelos

    return catalogo_modelos.modelo_imagem()


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


def _strip_b64(raw: str) -> tuple[str, str | None]:
    """Retorna (base64 puro, mime se data-URL)."""
    s = (raw or "").strip()
    mime = None
    if s.startswith("data:") and ";base64," in s:
        head, _, b64 = s.partition(";base64,")
        mime = head[5:] if head.startswith("data:") else None
        return b64.strip(), mime
    return s, None


def _audio_format(mime: str | None, nome: str = "") -> str:
    m = (mime or "").lower()
    n = (nome or "").lower()
    for fmt, keys in (
        ("mp3", ("mpeg", "mp3")),
        ("wav", ("wav", "wave")),
        ("ogg", ("ogg", "opus")),
        ("m4a", ("m4a", "mp4", "aac")),
        ("webm", ("webm",)),
        ("flac", ("flac",)),
    ):
        if any(k in m for k in keys) or any(n.endswith(f".{k}") for k in keys):
            return fmt
    return "mp3"


async def ler_pdf(params: dict[str, Any]) -> dict[str, Any]:
    """Lê PDF via OpenRouter: file + plugin mistral-ocr + Ministral (URL, data-URL ou base64)."""
    from apura import modelos as catalogo_modelos

    url = (params.get("url") or "").strip()
    texto = (params.get("texto") or "").strip()
    file_b64 = (params.get("file_base64") or params.get("data_base64") or "").strip()
    pergunta = (params.get("pergunta") or "Resuma os pontos relevantes para a campanha.").strip()
    if not url and not texto and not file_b64:
        return {
            "status": "vazio",
            "mensagem": "informe url, anexo (file_base64) ou texto do PDF",
            "nivel": "indicio",
        }

    model = catalogo_modelos.modelo_pdf()
    engine = catalogo_modelos.pdf_engine()

    if texto and not url and not file_b64:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Leia o documento. Indício apenas. Sem inventar cifras de urna.",
                },
                {"role": "user", "content": f"{pergunta}\n\n---\n{texto[:50000]}"},
            ],
            "temperature": 0.2,
        }
    else:
        filename = (params.get("filename") or params.get("nome") or "").strip()
        if file_b64:
            b64, mime = _strip_b64(file_b64)
            if len(b64) > _MAX_B64:
                return {
                    "status": "vazio",
                    "mensagem": "PDF anexo acima do limite (~4 MB)",
                    "nivel": "indicio",
                }
            mime = mime or (params.get("mime") or "application/pdf")
            file_data = f"data:{mime};base64,{b64}"
            if not filename:
                filename = "anexo.pdf"
        else:
            file_data = url
            if not filename:
                filename = url.rsplit("/", 1)[-1] or "documento.pdf"
        filename = filename[:120]
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você analisa documentos de campanha (PDF). "
                        "Indício apenas. Sem inventar cifras de urna. "
                        "Cite trechos quando possível."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": pergunta},
                        {
                            "type": "file",
                            "file": {"filename": filename, "file_data": file_data},
                        },
                    ],
                },
            ],
            "plugins": [{"id": "file-parser", "pdf": {"engine": engine}}],
            "temperature": 0.2,
        }

    async with httpx.AsyncClient(timeout=180.0) as client:
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
        "itens": [{"resumo": text[:12000], "fonte": f"pdf:{model}", "engine": engine}],
        "mensagem": None if text.strip() else "sem conteúdo extraído",
        "nota_metodologica": (
            f"PDF via OpenRouter ({engine} + {model}) — indício; cruzar com oficial se for cifra."
        ),
    }


async def ler_imagem(params: dict[str, Any]) -> dict[str, Any]:
    url = (params.get("url") or params.get("image_url") or "").strip()
    file_b64 = (params.get("file_base64") or params.get("data_base64") or "").strip()
    pergunta = (params.get("pergunta") or "Descreva o que é relevante para a campanha.").strip()
    if file_b64 and not url:
        b64, mime = _strip_b64(file_b64)
        if len(b64) > _MAX_B64:
            return {"status": "vazio", "mensagem": "imagem acima do limite (~4 MB)", "nivel": "indicio"}
        mime = mime or (params.get("mime") or "image/jpeg")
        url = f"data:{mime};base64,{b64}"
    if not url:
        return {
            "status": "vazio",
            "mensagem": "url ou anexo (file_base64) da imagem obrigatório",
            "nivel": "indicio",
        }
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
    """Transcreve áudio via input_audio (base64) ou baixa URL e envia em base64."""
    from apura import modelos as catalogo_modelos

    url = (params.get("url") or "").strip()
    file_b64 = (params.get("file_base64") or params.get("data_base64") or "").strip()
    mime = (params.get("mime") or "").strip() or None
    nome = (params.get("filename") or params.get("nome") or "").strip()
    pergunta = (
        params.get("pergunta")
        or "Transcreva em português BR e resuma pontos úteis para campanha. Se não ouvir, diga lacuna."
    ).strip()

    b64 = ""
    if file_b64:
        b64, mime_from = _strip_b64(file_b64)
        mime = mime or mime_from
    elif url.startswith("data:") and ";base64," in url:
        b64, mime_from = _strip_b64(url)
        mime = mime or mime_from
    elif url.startswith("http://") or url.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
                ar = await client.get(url)
            if ar.status_code >= 400:
                return {
                    "status": "vazio",
                    "mensagem": f"não foi possível baixar o áudio ({ar.status_code})",
                    "nivel": "indicio",
                }
            raw = ar.content
            if len(raw) > 4_000_000:
                return {
                    "status": "vazio",
                    "mensagem": "áudio remoto acima de 4 MB",
                    "nivel": "indicio",
                }
            b64 = base64.b64encode(raw).decode("ascii")
            mime = mime or (ar.headers.get("content-type") or "").split(";")[0].strip() or None
        except Exception as exc:
            return {
                "status": "vazio",
                "mensagem": f"falha ao baixar áudio: {exc}",
                "nivel": "indicio",
            }
    else:
        return {
            "status": "vazio",
            "mensagem": "informe anexo (file_base64) ou url http(s) do áudio",
            "nivel": "indicio",
        }

    if not b64 or len(b64) > _MAX_B64:
        return {
            "status": "vazio",
            "mensagem": "áudio vazio ou acima do limite (~4 MB)",
            "nivel": "indicio",
        }

    fmt = _audio_format(mime, nome)
    model = catalogo_modelos.modelo_audio()
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": pergunta},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": b64, "format": fmt},
                    },
                ],
            }
        ],
        "temperature": 0.1,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(_OPENROUTER, headers=_headers(), json=body)
    if r.status_code >= 400:
        return {
            "status": "vazio",
            "mensagem": f"transcrição indisponível ({r.status_code})",
            "nivel": "indicio",
            "nota_metodologica": (r.text or "")[:400],
        }
    text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {
        "status": "ok" if text.strip() else "vazio",
        "nivel": "indicio",
        "itens": [{"resumo": text[:8000], "fonte": f"audio:{model}", "format": fmt}],
        "nota_metodologica": "Áudio = indício (input_audio OpenRouter).",
    }


def _extrair_imagem_resposta(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Retorna (data_url ou https url, nota)."""
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0] if isinstance(items[0], dict) else {}
        b64 = first.get("b64_json") or first.get("b64")
        if b64:
            mime = first.get("mime_type") or "image/png"
            return f"data:{mime};base64,{b64}", "images_api"
        u = first.get("url")
        if u:
            return str(u), "images_api_url"
    # fallback chat modalities
    msg = ((data.get("choices") or [{}])[0].get("message") or {}) if data.get("choices") else {}
    images = msg.get("images") or []
    if images and isinstance(images[0], dict):
        iu = (images[0].get("image_url") or {}).get("url") or images[0].get("url")
        if iu:
            return str(iu), "chat_modalities"
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("image_url", "output_image"):
                iu = (part.get("image_url") or {}).get("url") or part.get("url")
                if iu:
                    return str(iu), "chat_content"
    return None, None


async def gerar_imagem(params: dict[str, Any]) -> dict[str, Any]:
    """Gera imagem real via OpenRouter POST /api/v1/images."""
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        return {"status": "vazio", "mensagem": "prompt obrigatório", "nivel": "artefato"}
    ctx = (params.get("contexto_campanha") or "")[:600]
    full = prompt if not ctx else f"{prompt}\n\nContexto de campanha (não invente cifra): {ctx}"
    aspect = (params.get("aspect_ratio") or "16:9").strip()
    model = _model_image()
    body: dict[str, Any] = {
        "model": model,
        "prompt": full[:4000],
        "aspect_ratio": aspect,
        "n": 1,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(_OPENROUTER_IMAGES, headers=_headers(), json=body)
    if r.status_code >= 400:
        # fallback: storyboard texto para não quebrar fluxo
        story = {
            "model": _model_vision(),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "A geração de imagem falhou. Entregue um storyboard detalhado "
                        f"(cenário, luz, texto na peça) para produção. Pedido: {full}"
                    ),
                }
            ],
        }
        async with httpx.AsyncClient(timeout=90.0) as client2:
            r2 = await client2.post(_OPENROUTER, headers=_headers(), json=story)
        text = ""
        if r2.status_code < 400:
            text = (r2.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return {
            "status": "parcial" if text.strip() else "vazio",
            "nivel": "artefato",
            "itens": [{"descricao": text[:8000]}] if text.strip() else [],
            "mensagem": f"API de imagem indisponível ({r.status_code}) — storyboard em texto",
            "nota_metodologica": (r.text or "")[:400],
        }

    data = r.json()
    image_url, via = _extrair_imagem_resposta(data)
    if not image_url:
        return {
            "status": "vazio",
            "mensagem": "API de imagem não retornou bytes/URL",
            "nivel": "artefato",
            "nota_metodologica": json.dumps(data)[:400],
        }
    # Não persistir b64 gigante no tool_log resumido — UI pega do done.imagem
    item: dict[str, Any] = {"fonte": f"imagem:{model}", "via": via, "prompt": prompt[:500]}
    out: dict[str, Any] = {
        "status": "ok",
        "nivel": "artefato",
        "itens": [item],
        "image_url": image_url if image_url.startswith("http") else None,
        "image_data_url": image_url if image_url.startswith("data:") else None,
        "nota_metodologica": "Artefato visual gerado — não é dado oficial.",
    }
    return out


async def gerar_mapa_html(params: dict[str, Any]) -> dict[str, Any]:
    """Plano/mapa estratégico HTML via template determinístico (bem feito, estável)."""
    from apura.plano_html import enriquecer_params_do_ctx, montar_plano_html

    titulo = (params.get("titulo") or "Plano estratégico").strip()[:120]
    eixos = (params.get("eixos") or params.get("conteudo") or "").strip()
    if not eixos:
        return {
            "status": "vazio",
            "mensagem": "informe eixos/conteudo do plano (linhas Título: detalhe)",
            "nivel": "artefato",
        }
    p = enriquecer_params_do_ctx(params, params.get("contexto_campanha") or "")
    html = montar_plano_html(
        titulo=titulo,
        eixos_raw=eixos[:8000],
        nosso=(p.get("nosso") or "")[:80],
        rival=(p.get("rival") or "")[:80],
        contexto=(p.get("contexto") or p.get("contexto_campanha") or "")[:1200],
        leituras=(p.get("leituras") or "")[:2000],
        proximo=(p.get("proximo") or p.get("proximo_passo") or "")[:800],
    )
    return {
        "status": "ok",
        "nivel": "artefato",
        "html": html[:100000],
        "titulo": titulo,
        "nota_metodologica": "Plano HTML template Apura — artefato, não urna.",
    }


async def gerar_plano_html(params: dict[str, Any]) -> dict[str, Any]:
    """Alias explícito de gerar_mapa_html (plano estratégico visual)."""
    return await gerar_mapa_html(params)


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


async def consultar_memoria_campanha(
    params: dict[str, Any],
    *,
    campanha_id: str | None = None,
) -> dict[str, Any]:
    if not campanha_id:
        return {
            "status": "vazio",
            "mensagem": "sem campanha no token — memória indisponível",
            "nivel": "indicio",
        }
    url = _db_url()
    if not url:
        return {"status": "vazio", "mensagem": "banco indisponível", "nivel": "indicio"}
    from gestao import memoria as gestao_memoria

    with psycopg.connect(url) as conn:
        return gestao_memoria.consultar_para_apura(
            conn,
            campanha_id,
            tipo=(params.get("tipo") or None),
            query=(params.get("query") or None),
            limite=int(params.get("limite") or 8),
        )


LOCAL_METHODS = frozenset(
    {
        "pesquisar_web",
        "ler_pdf",
        "ler_imagem",
        "transcrever_audio",
        "gerar_imagem",
        "gerar_mapa_html",
        "gerar_plano_html",
        "consultar_memoria",
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
    if method in ("gerar_mapa_html", "gerar_plano_html"):
        return await gerar_mapa_html(p)
    if method == "consultar_memoria":
        return await consultar_memoria_campanha(p, campanha_id=campanha_id)
    if method == "operacional_contato":
        return operacional_contato(p, campanha_id=campanha_id)
    if method == "operacional_tarefa":
        return operacional_tarefa(p, campanha_id=campanha_id, usuario_id=usuario_id)
    return {"erro": f"método local desconhecido: {method}"}
