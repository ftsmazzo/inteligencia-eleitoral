"""Exports das camadas de prompt (compatível com imports antigos via apura.prompt)."""

from apura.prompts.orquestrador import (
    NARRATIVA_ORCHESTRATOR,
    SKILL_NARRATIVA_DEFAULT,
    SKILL_WAR_ROOM_DEFAULT,
    SYSTEM_ORCHESTRATOR,
)
from apura.prompts.politica_dados import POLITICA_DADOS, RECORTE_BRASIL
from apura.prompts.protocolo_airy import (
    PROTOCOLO_AIRY_CRIACAO,
    PROTOCOLO_AIRY_ELEITORAL,
    PROTOCOLO_ANALISTA,
    PROTOCOLO_OPERACIONAL,
)
from apura.prompts.voz import VOZ_OPERACIONAL, VOZ_REDATOR

# Alias legado
SYSTEM_WRITER = VOZ_REDATOR

__all__ = [
    "NARRATIVA_ORCHESTRATOR",
    "SYSTEM_ORCHESTRATOR",
    "SYSTEM_WRITER",
    "VOZ_REDATOR",
    "VOZ_OPERACIONAL",
    "SKILL_WAR_ROOM_DEFAULT",
    "SKILL_NARRATIVA_DEFAULT",
    "POLITICA_DADOS",
    "RECORTE_BRASIL",
    "PROTOCOLO_AIRY_ELEITORAL",
    "PROTOCOLO_AIRY_CRIACAO",
    "PROTOCOLO_OPERACIONAL",
    "PROTOCOLO_ANALISTA",
]
