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


def extrair_identidade_visual(ctx: str) -> dict[str, str]:
    """Puxa nome/UF/cargo/ano do bloco de escopo/identidade injetado no hub."""
    c = ctx or ""
    out: dict[str, str] = {}
    m = re.search(
        r"(?:Nosso candidato|candidato monitorado)[^\n:]{0,40}:\s*([^\n(]+)",
        c,
        re.I,
    )
    if m:
        out["nosso"] = m.group(1).strip()[:80]
    m = re.search(r"- UF:\s*([A-Za-z]{2})\b", c)
    if m:
        out["uf"] = m.group(1).upper()
    m = re.search(r"- Cargo:\s*([^\n]+)", c)
    if m:
        out["cargo"] = m.group(1).strip()[:60]
    m = re.search(r"- Ano:\s*(\d{4})", c)
    if m:
        out["ano"] = m.group(1)
    m = re.search(r"- Munic[ií]pio[^\n:]*:\s*([^\n]+)", c, re.I)
    if m:
        out["municipio"] = m.group(1).strip()[:80]
    m = re.search(r"- Partido[^\n:]*:\s*([^\n]+)", c, re.I)
    if m:
        out["partido"] = m.group(1).strip()[:40]
    m = re.search(r"Rival\(is\) de campanha[^:\n]*:\s*([^\n;]+)", c, re.I)
    if m and "ainda não" not in m.group(1).lower():
        out["rival"] = m.group(1).strip()[:60]
    return out


def montar_prompt_imagem_campanha(pedido: str, contexto_campanha: str = "") -> str:
    """Briefing visual amarrado à campanha — evita arte genérica sem candidato."""
    idn = extrair_identidade_visual(contexto_campanha)
    nome = idn.get("nosso") or ""
    cargo = idn.get("cargo") or "candidato"
    uf = idn.get("uf") or "Brasil"
    ano = idn.get("ano") or ""
    municipio = idn.get("municipio") or ""
    partido = idn.get("partido") or ""
    territorio = ", ".join(x for x in (municipio, uf) if x) or uf
    pedido_limpo = (pedido or "").strip()[:700]

    # Se o usuário já citou o nome, não duplicar de forma confusa
    if not nome:
        m = re.search(
            r"(?:capa|imagem|arte|para|do|da|de)\s+([A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁÉÍÓÚÂÊÔÃÕáéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁÉÍÓÚÂÊÔÃÕáéíóúâêôãõç]+){0,3})",
            pedido_limpo,
        )
        if m:
            nome = m.group(1).strip()[:80]

    hero = nome or "NOME DO CANDIDATO (obrigatório na tipografia)"
    linhas = [
        "Brazilian political campaign poster / social graphic, professional war-room design.",
        f"HERO TEXT (must be readable on the artwork): \"{hero}\"",
        f"Office/role: {cargo}. Territory: {territorio}."
        + (f" Election year: {ano}." if ano else ""),
    ]
    if partido:
        linhas.append(f"Party cue (subtle, not a logo copy): {partido}.")
    linhas.extend(
        [
            "Layout: clean campaign cover — strong typography, Brazilian local atmosphere "
            f"for {territorio}, confident colors, not US election stock.",
            "Style: graphic design poster (typography-first). Do NOT invent photorealistic "
            "faces of real people; if a person appears, keep stylized/silhouette.",
            "Forbidden: fake poll numbers, TSE logos, QR codes, watermark clutter, "
            "generic 'vote' art without the candidate name.",
            f"User brief: {pedido_limpo or 'capa de campanha'}",
        ]
    )
    return "\n".join(linhas)


def comprimir_data_url_imagem(
    data_url: str,
    *,
    max_side: int = 1280,
    max_chars: int = 700_000,
    quality: int = 78,
) -> str:
    """Reduz data-URL (JPEG) para caber no histórico do chat."""
    if not data_url.startswith("data:") or ";base64," not in data_url:
        return data_url
    head = data_url[:48].lower()
    precisa = (
        len(data_url) > max_chars
        or "image/png" in head
        or "image/webp" in head
        or len(data_url) > int(max_chars * 0.55)
    )
    if not precisa:
        return data_url
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        return data_url

    b64, _mime = _strip_b64(data_url)
    try:
        raw = base64.b64decode(b64)
        img = Image.open(BytesIO(raw))
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        q = quality
        out = data_url
        for _ in range(8):
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            out = f"data:image/jpeg;base64,{encoded}"
            if len(out) <= max_chars:
                return out
            q = max(35, q - 10)
            if max(img.size) > 640:
                nw = int(img.size[0] * 0.75)
                nh = int(img.size[1] * 0.75)
                img = img.resize((max(1, nw), max(1, nh)), Image.Resampling.LANCZOS)
        return out
    except Exception:
        return data_url


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
        or "Transcreva fielmente em português BR. Se for um pedido ou pergunta, preserve o texto exatamente, sem inventar."
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


def _pacote_imagem_ok(
    *,
    image_url: str,
    via: str | None,
    model: str,
    prompt_usado: str,
) -> dict[str, Any]:
    """Normaliza URL/data-URL: comprime base64 para caber no histórico."""
    url_http = image_url if image_url.startswith("http") else None
    data = image_url if image_url.startswith("data:") else None
    if data:
        data = comprimir_data_url_imagem(data, max_side=1280, max_chars=700_000, quality=78)
    return {
        "status": "ok",
        "nivel": "artefato",
        "itens": [
            {
                "fonte": f"imagem:{model}",
                "via": via,
                "prompt": prompt_usado[:700],
                "bytes_aprox": len(data) if data else None,
            }
        ],
        "image_url": url_http,
        "image_data_url": data,
        "nota_metodologica": "Artefato visual gerado (comprimido p/ histórico) — não é dado oficial.",
    }


async def gerar_imagem(params: dict[str, Any]) -> dict[str, Any]:
    """Gera imagem real via OpenRouter POST /api/v1/images (fallback: chat modalities)."""
    pedido = (params.get("prompt") or "").strip()
    if not pedido:
        return {"status": "vazio", "mensagem": "prompt obrigatório", "nivel": "artefato"}
    ctx = (params.get("contexto_campanha") or "")[:2500]
    # Briefing amarrado à campanha (nome/UF/cargo) — evita arte genérica
    full = montar_prompt_imagem_campanha(pedido, ctx)
    aspect = (params.get("aspect_ratio") or "16:9").strip()
    model = _model_image()
    body: dict[str, Any] = {
        "model": model,
        "prompt": full[:3500],
        "aspect_ratio": aspect,
        "n": 1,
        # Limita payload: 1K + jpeg (OpenRouter Images)
        "resolution": (params.get("resolution") or "1K").strip() or "1K",
        "output_format": "jpeg",
        "output_compression": 75,
    }
    err_txt = ""
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(_OPENROUTER_IMAGES, headers=_headers(), json=body)
        if r.status_code < 400:
            image_url, via = _extrair_imagem_resposta(r.json())
            if image_url:
                return _pacote_imagem_ok(
                    image_url=image_url,
                    via=via,
                    model=model,
                    prompt_usado=full,
                )
            err_txt = (r.text or "")[:400]
        else:
            err_txt = (r.text or "")[:400]
            # Retry sem params opcionais (alguns provedores rejeitam)
            body_min = {
                "model": model,
                "prompt": full[:3500],
                "aspect_ratio": aspect,
                "n": 1,
            }
            r_min = await client.post(_OPENROUTER_IMAGES, headers=_headers(), json=body_min)
            if r_min.status_code < 400:
                image_url, via = _extrair_imagem_resposta(r_min.json())
                if image_url:
                    return _pacote_imagem_ok(
                        image_url=image_url,
                        via=via or "images_api_min",
                        model=model,
                        prompt_usado=full,
                    )
            # Fallback: chat completions com modalities
            chat_body = {
                "model": model,
                "messages": [{"role": "user", "content": full[:3500]}],
                "modalities": ["image", "text"],
            }
            r2 = await client.post(_OPENROUTER, headers=_headers(), json=chat_body)
            if r2.status_code < 400:
                image_url, via = _extrair_imagem_resposta(r2.json())
                if image_url:
                    return _pacote_imagem_ok(
                        image_url=image_url,
                        via=via or "chat_modalities",
                        model=model,
                        prompt_usado=full,
                    )
            # Storyboard texto
            story = {
                "model": _model_vision(),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "A geração de imagem falhou. Entregue um storyboard detalhado "
                            f"(tipografia com NOME do candidato, cores, layout) para produção.\n{full}"
                        ),
                    }
                ],
            }
            r3 = await client.post(_OPENROUTER, headers=_headers(), json=story)
            text = ""
            if r3.status_code < 400:
                text = (r3.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
            return {
                "status": "parcial" if text.strip() else "vazio",
                "nivel": "artefato",
                "itens": [{"descricao": text[:8000], "prompt": full[:700]}] if text.strip() else [],
                "mensagem": f"API de imagem indisponível ({r.status_code}) — storyboard em texto",
                "nota_metodologica": err_txt,
            }

    return {
        "status": "vazio",
        "mensagem": "API de imagem não retornou bytes/URL",
        "nivel": "artefato",
        "nota_metodologica": err_txt,
    }

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
