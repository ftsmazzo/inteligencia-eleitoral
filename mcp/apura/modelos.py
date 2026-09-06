"""Catálogo de modelos OpenRouter por função — custo × qualidade.

Princípio: cada papel usa a IA que combina com a tarefa.
- Orquestração / tools → Gemini Flash/Pro (barato, tool-calling forte)
- Texto final / reflexão → Anthropic Claude Sonnet (prosa e julgamento)
- Web → Perplexity Sonar
- PDF → Ministral 3 14B + engine OpenRouter `mistral-ocr` (OCR Mistral)
- Visão genérica → Gemini Flash
- Triagem operacional → DeepSeek V4 Flash ou Haiku

Overrides por env sempre ganham. IDs verificados no catálogo OpenRouter.
"""
from __future__ import annotations

import os
from typing import Any

# --- Defaults por função (produção) -----------------------------------------

# Tool-calling / plano de agentes — custo baixo, boa adesão a tools
ORCH_PADRAO = "google/gemini-2.5-flash"
ORCH_ARY = "google/gemini-2.5-pro"

# Redação final, reflexão, voz de campanha — Anthropic
REDATOR_PADRAO = "anthropic/claude-sonnet-4.6"
REDATOR_ARY = "anthropic/claude-sonnet-5"

# Perfis (quando ctl.perfil não sobrescreve)
PERFIL_MODELOS: dict[str, dict[str, str]] = {
    "consultor_minimo": {
        "orquestrador": "google/gemini-2.5-flash-lite",
        "redator": "anthropic/claude-haiku-4.5",
    },
    "analista": {
        "orquestrador": ORCH_PADRAO,
        "redator": REDATOR_PADRAO,
    },
    "estrategista": {
        "orquestrador": ORCH_ARY,
        "redator": REDATOR_PADRAO,
    },
    "coordenador": {
        "orquestrador": ORCH_ARY,
        "redator": REDATOR_PADRAO,
    },
}

# Capacidades / agentes especializados
WEB = "perplexity/sonar"
WEB_ARY = "perplexity/sonar-pro"
# PDF: OCR Mistral (plugin) + Ministral 3 14B (visão/doc, barato, 256k)
PDF = "mistralai/ministral-14b-2512"
PDF_ENGINE = "mistral-ocr"  # file-parser: melhor em scan/imagens; ~$2/1k páginas
VISAO = "google/gemini-2.5-flash"
AUDIO = "openai/gpt-4o-audio-preview"  # niche; override se houver melhor
IMAGEM = "google/gemini-2.5-flash-image"
MAPA_HTML = REDATOR_PADRAO  # HTML estratégico = prosa estruturada
GOVERNANCA = "google/gemini-2.5-flash-lite"
RADAR = "google/gemini-2.5-flash"
TRIAGEM = "deepseek/deepseek-v4-flash"

# Agente lógico → modelo preferido (quando houver LLM dedicado no futuro)
AGENTE_MODELO: dict[str, str] = {
    "dados": ORCH_PADRAO,  # hoje SQL; se resumir, Flash basta
    "clima": ORCH_PADRAO,
    "acervo": REDATOR_PADRAO,  # síntese de planos = texto
    "web": WEB,
    "media": PDF,
    "visual": IMAGEM,
    "operacional": "anthropic/claude-haiku-4.5",
}


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or "").strip() or default


def orquestrador(*, ary: bool = False, perfil_slug: str | None = None) -> str:
    """Modelo do orquestrador. Env global força; senão perfil; senão Flash/Pro."""
    if ary:
        return _env("APURA_ARY_ORCHESTRATOR_MODEL", ORCH_ARY)
    forced = (os.environ.get("APURA_ORCHESTRATOR_MODEL") or os.environ.get("APURA_MODEL") or "").strip()
    if forced:
        return forced
    if perfil_slug and perfil_slug in PERFIL_MODELOS:
        return PERFIL_MODELOS[perfil_slug]["orquestrador"]
    return ORCH_PADRAO


def redator(*, ary: bool = False, perfil_slug: str | None = None) -> str:
    """Modelo do redator final. Env Ary/global; senão perfil; senão Sonnet."""
    if ary:
        return _env("APURA_ARY_WRITER_MODEL", REDATOR_ARY)
    forced = (os.environ.get("APURA_WRITER_MODEL") or "").strip()
    if forced:
        return forced
    if perfil_slug and perfil_slug in PERFIL_MODELOS:
        return PERFIL_MODELOS[perfil_slug]["redator"]
    return REDATOR_PADRAO


def redator_fallback_env() -> str:
    """Fallback para perfil_policy quando o banco não tem modelo."""
    return _env("APURA_WRITER_MODEL", REDATOR_PADRAO)


def orch_fallback_env() -> str:
    return _env(
        "APURA_ORCHESTRATOR_MODEL",
        _env("APURA_MODEL", ORCH_PADRAO),
    )


def modelo_web(*, ary: bool = False) -> str:
    return _env("APURA_WEB_MODEL", WEB_ARY if ary else WEB)


def modelo_pdf() -> str:
    return _env("APURA_PDF_MODEL", PDF)


def pdf_engine() -> str:
    """OpenRouter file-parser: mistral-ocr | cloudflare-ai | native."""
    return _env("APURA_PDF_ENGINE", PDF_ENGINE)


def modelo_visao() -> str:
    return _env("APURA_VISION_MODEL", VISAO)


def modelo_audio() -> str:
    return _env("APURA_AUDIO_MODEL", AUDIO)


def modelo_imagem() -> str:
    return _env("APURA_IMAGE_MODEL", IMAGEM)


def modelo_mapa_html() -> str:
    return _env("APURA_MAPA_HTML_MODEL", MAPA_HTML)


def modelo_governanca() -> str:
    return _env("APURA_GOVERNANCA_MODEL", GOVERNANCA)


def modelo_radar() -> str:
    return _env(
        "APURA_RADAR_MODEL",
        _env("APURA_ORCHESTRATOR_MODEL", RADAR),
    )


def modelo_agente(nome: str) -> str:
    return AGENTE_MODELO.get(nome, ORCH_PADRAO)


def catalogo() -> dict[str, Any]:
    """Para docs / debug — o que cada papel usa."""
    return {
        "orquestrador_padrao": ORCH_PADRAO,
        "orquestrador_ary": ORCH_ARY,
        "redator_padrao": REDATOR_PADRAO,
        "redator_ary": REDATOR_ARY,
        "perfis": PERFIL_MODELOS,
        "agentes": AGENTE_MODELO,
        "web": WEB,
        "web_ary": WEB_ARY,
        "pdf": PDF,
        "pdf_engine": PDF_ENGINE,
        "visao": VISAO,
        "audio": AUDIO,
        "imagem": IMAGEM,
        "governanca": GOVERNANCA,
        "radar": RADAR,
        "nota": (
            "Anthropic no texto final; Gemini no roteamento/tools; "
            "PDF = Ministral 14B + mistral-ocr; Perplexity na web; "
            "DeepSeek/Haiku em triagem barata."
        ),
    }
