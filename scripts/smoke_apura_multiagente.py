#!/usr/bin/env python3
"""Smoke estático · Apura multiagente (Fase 0–4).

Roda sem banco/OpenRouter: valida imports, registry, MissaoState e tools.
Uso: python scripts/smoke_apura_multiagente.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "mcp"
sys.path.insert(0, str(MCP))


def main() -> int:
    errors: list[str] = []

    try:
        from apura.missao_state import (
            MissaoState,
            aplicar_comando,
            detectar_comando,
            estado_inicial,
            perfil_de_slug,
        )
        from apura.prompt import SYSTEM_ORCHESTRATOR, SYSTEM_WRITER, VOZ_REDATOR
        from apura.agents.registry import AGENTE_POR_TOOL, camada_da_tool
        from apura.tools import MCP_TOOLS, TOOL_TO_MCP
        from apura.capabilities import LOCAL_METHODS
        from apura.orchestrator import executar_chat
        from apura.agents.hub import executar_hub
    except Exception as exc:
        print(f"FAIL import: {exc}")
        return 1

    assert SYSTEM_ORCHESTRATOR and SYSTEM_WRITER and VOZ_REDATOR
    assert executar_chat is not None and executar_hub is not None

    # Perfis
    assert perfil_de_slug("consultor_minimo").value == "operacional"
    assert perfil_de_slug("estrategista").value == "estrategista"
    assert perfil_de_slug("coordenador").value == "estrategista"

    st = estado_inicial("estrategista")
    assert detectar_comando("Ativar Ary") == "ativar"
    st = aplicar_comando(st, "ativar", "Ativar Ary")
    assert st.protocolo_ativo and st.etapa == "briefing_objetivo"
    st = aplicar_comando(st, None, "Quero um dossiê do adversário")
    assert st.aguardando_ok and st.objetivo
    st = aplicar_comando(st, "ok", "OK")
    assert st.etapa == "briefing_estilo"

    st_op = estado_inicial("consultor_minimo")
    assert st_op.caminho_curto

    # Tools novas no mapa
    novas = [
        "pesquisar_web",
        "ler_pdf",
        "ler_imagem",
        "transcrever_audio",
        "gerar_imagem",
        "gerar_mapa_html",
        "operacional_contato",
        "operacional_tarefa",
    ]
    names = {(t.get("function") or {}).get("name") for t in MCP_TOOLS}
    for n in novas:
        if n not in names:
            errors.append(f"tool ausente em MCP_TOOLS: {n}")
        if n not in TOOL_TO_MCP:
            errors.append(f"tool ausente em TOOL_TO_MCP: {n}")
        if TOOL_TO_MCP.get(n) not in LOCAL_METHODS:
            errors.append(f"method local ausente: {TOOL_TO_MCP.get(n)}")

    assert camada_da_tool("consultar_votacao") == "fato"
    assert camada_da_tool("consultar_clima") == "indicio_clima"
    assert camada_da_tool("pesquisar_web") == "indicio_web"
    assert AGENTE_POR_TOOL.get("gerar_mapa_html") == "visual"

    # Serialização MissaoState
    d = MissaoState(perfil="estrategista", protocolo_ativo=True).to_dict()
    assert MissaoState.from_dict(d).protocolo_ativo

    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1

    print("OK smoke_apura_multiagente")
    print(f"  tools MCP: {len(MCP_TOOLS)}")
    print(f"  locais: {sorted(LOCAL_METHODS)}")
    print("  MissaoState + hub + prompts: ok")
    print("  Checklist humano pos-deploy:")
    print("    1. Login super -> Operar Amapa -> Chat cifra 2022")
    print("    2. Operar vice -> contexto troca")
    print("    3. Estrategista: 'Ativar Ary' inicia briefing")
    print("    4. Operacional: contato/tarefa")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
