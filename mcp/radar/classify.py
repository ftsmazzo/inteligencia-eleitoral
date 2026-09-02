"""Classificação LLM do Radar via OpenRouter (fallback pendente)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

PROMPT_CLIMA = (
    "Voce e analista de inteligencia eleitoral. Ponto de vista: o candidato monitorado. "
    "Score -100 a 100. tipo: ataque|defesa|escandalo|rotina|oportunidade|boato|cobertura. "
    "urgencia: baixa|media|alta|critica. "
    "Responda so JSON: synthesis, score, polarity, risk, tipo, urgencia, action_respond."
)

PROMPT_MIX = (
    "Voce classifica pecas oficiais da campanha nos eixos estrategicos. "
    "Escolha UM eixo da lista. Se nao couber, eixo=outros. "
    "Responda so JSON: synthesis, eixo, tipo (rotina|mobilizacao|entrega|enfrentamento), "
    "urgencia (baixa|media|alta)."
)


def _model() -> str:
    return (
        os.environ.get("RADAR_CLASSIFY_MODEL")
        or os.environ.get("APURA_ORCHESTRATOR_MODEL")
        or os.environ.get("APURA_MODEL")
        or "openai/gpt-4o-mini"
    )


def _key() -> str:
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def _parse_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _llm_json(system: str, user: str) -> tuple[dict[str, Any], str]:
    key = _key()
    if not key:
        return {}, ""
    model = _model()
    body = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get(
            "APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"
        ),
        "X-Title": "Radar Inteligencia Dados",
    }
    r = httpx.post(_OPENROUTER, headers=headers, json=body, timeout=60.0)
    r.raise_for_status()
    data = r.json()
    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    )
    return _parse_json(content), model


def classify_clima(titulo: str, body: str, alvo: str) -> dict[str, Any]:
    fallback = {
        "synthesis": "Coletado. Classificacao pendente.",
        "score": 0,
        "polarity": "neutro",
        "risk": "medio",
        "tipo": "cobertura",
        "urgencia": "media",
        "eixo": "",
        "action_respond": "Aguardar classificacao.",
        "_model": "",
    }
    raw = (body or "").strip()
    if len(raw) < 12 and len((titulo or "").strip()) < 12:
        fallback["synthesis"] = "Sem texto suficiente para classificar. Abra o link."
        fallback["tipo"] = "rotina"
        fallback["urgencia"] = "baixa"
        return fallback
    user = f"Alvo: {alvo}\nTitulo: {titulo}\nTexto: {(raw or titulo)[:4500]}"
    try:
        data, model = _llm_json(PROMPT_CLIMA, user)
        if not data:
            return fallback
        fallback.update(data)
        fallback["score"] = max(-100, min(100, int(fallback.get("score") or 0)))
        fallback["_model"] = model
        return fallback
    except Exception as e:
        fallback["synthesis"] = f"Coletado. Classificacao pendente ({e})."
        return fallback


def classify_mix(titulo: str, body: str, eixos: list[tuple[str, str]]) -> dict[str, Any]:
    names = [n for n, _ in eixos] or ["outros"]
    catalog = "; ".join(f"{n} ({h or '-'})" for n, h in eixos) or "outros"
    fallback = {
        "synthesis": "Peca oficial gravada.",
        "score": 0,
        "polarity": "neutro",
        "risk": "baixo",
        "tipo": "rotina",
        "urgencia": "baixa",
        "eixo": "outros",
        "action_respond": "",
        "_model": "",
    }
    user = f"Eixos permitidos: {catalog}\nTitulo: {titulo}\nTexto: {(body or '')[:4000]}"
    try:
        data, model = _llm_json(PROMPT_MIX, user)
        if data:
            fallback.update(data)
        eixo = str(fallback.get("eixo") or "outros").strip()
        if eixo not in names and eixo.lower() != "outros":
            eixo = "outros"
        fallback["eixo"] = eixo
        fallback["score"] = 0
        fallback["_model"] = model
        return fallback
    except Exception as e:
        fallback["synthesis"] = f"Peca oficial gravada. Eixo pendente ({e})."
        return fallback
