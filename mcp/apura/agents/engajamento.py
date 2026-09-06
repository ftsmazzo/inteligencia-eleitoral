"""Playbook duro de engajamento: estratégia/ângulo exige clima (e web se clima vazio)."""
from __future__ import annotations

import re
from typing import Any

_PEDIDO_ESTRATEGIA = re.compile(
    r"estrat[eé]g|ângulo|angulo|contraste|narrativa|o\s+que\s+dizer|"
    r"como\s+(?:atacar|responder|enfrentar)|contra\s+o\s+rival|"
    r"dossi[eê]\s+de\s+contraste|war\s*room|posicion",
    re.I,
)

_PEDIDO_RIVAL = re.compile(r"rival|advers[aá]rio|\beles\b|oponente", re.I)

_RIVAL_LINHA = re.compile(
    r"Rival\(is\) de campanha[^:\n]*:\s*([^\n]+)",
    re.I,
)


def pedido_exige_engajamento(pergunta: str) -> bool:
    """Estratégia/ângulo/contraste — ou rival + pedido analítico implícito."""
    p = (pergunta or "").strip()
    if not p:
        return False
    if _PEDIDO_ESTRATEGIA.search(p):
        return True
    # "fale do rival" curto = identidade; "estratégia contra rival" já caiu acima.
    # Se pede rival + clima/redes/pesquisa → engaja.
    if _PEDIDO_RIVAL.search(p) and re.search(
        r"clima|rede|not[ií]cia|pesquisa|instagram|web|tempo\s+real",
        p,
        re.I,
    ):
        return True
    return False


def rival_principal_do_ctx(campanha_ctx: str) -> str | None:
    m = _RIVAL_LINHA.search(campanha_ctx or "")
    if not m or "ainda não nomeados" in m.group(1).lower():
        return None
    primeiro = m.group(1).split(";")[0].strip()
    return primeiro[:120] if primeiro else None


def nosso_do_ctx(campanha_ctx: str) -> str | None:
    m = re.search(
        r"(?:Nosso candidato|candidato monitorado)[^\n:]{0,40}:\s*([^\n(]+)",
        campanha_ctx or "",
        re.I,
    )
    if not m:
        return None
    return m.group(1).strip()[:120] or None


def _tools_usadas(tool_log: list[dict[str, Any]]) -> set[str]:
    return {(t.get("tool") or "") for t in tool_log}


def clima_ja_consultado(tool_log: list[dict[str, Any]]) -> bool:
    return "consultar_clima" in _tools_usadas(tool_log)


def web_ja_consultada(tool_log: list[dict[str, Any]]) -> bool:
    return "pesquisar_web" in _tools_usadas(tool_log)


def resultado_clima_vazio(tool_log: list[dict[str, Any]]) -> bool:
    for t in tool_log:
        if t.get("tool") != "consultar_clima":
            continue
        res = t.get("result")
        if not isinstance(res, dict):
            return True
        if res.get("status") in ("vazio", "erro") or res.get("erro"):
            return True
        itens = res.get("itens") or res.get("linhas") or []
        if isinstance(itens, list) and len(itens) == 0:
            return True
        return False
    return True


def plano_engajamento_forcado(
    pergunta: str,
    campanha_ctx: str,
    tool_log: list[dict[str, Any]],
    *,
    tool_ok,
) -> list[dict[str, Any]]:
    """Retorna chamadas extras {tool, params} a executar antes do redator."""
    if not pedido_exige_engajamento(pergunta):
        return []
    if not (campanha_ctx or "").strip():
        return []

    rival = rival_principal_do_ctx(campanha_ctx)
    nosso = nosso_do_ctx(campanha_ctx)
    alvo = rival or nosso
    if not alvo:
        return []

    extras: list[dict[str, Any]] = []
    if tool_ok("consultar_memoria") and "consultar_memoria" not in _tools_usadas(tool_log):
        extras.append(
            {
                "tool": "consultar_memoria",
                "params": {"tipo": "estrategias", "limite": 3},
                "motivo": "playbook_estrategia_exige_memoria",
            }
        )
        extras.append(
            {
                "tool": "consultar_memoria",
                "params": {"tipo": "dossie_pesquisas", "limite": 3},
                "motivo": "playbook_estrategia_exige_pesquisas",
            }
        )
    if not clima_ja_consultado(tool_log) and tool_ok("consultar_clima"):
        extras.append(
            {
                "tool": "consultar_clima",
                "params": {
                    "q": alvo,
                    "canal": "news",
                    "janela_horas": 168,
                },
                "motivo": "playbook_estrategia_exige_clima",
            }
        )
    # Se já havia clima vazio, ou acabamos de planejar só clima e sabemos que
    # pode falhar — web como reforço de tempo real quando permitido.
    precisa_web = web_ja_consultada(tool_log) is False and tool_ok("pesquisar_web")
    if precisa_web and (clima_ja_consultado(tool_log) and resultado_clima_vazio(tool_log)):
        extras.append(
            {
                "tool": "pesquisar_web",
                "params": {
                    "query": f"{alvo} eleições notícias pesquisa intenção de voto",
                },
                "motivo": "playbook_clima_vazio_web",
            }
        )
    elif precisa_web and not clima_ja_consultado(tool_log) and tool_ok("consultar_clima"):
        # Agenda web em seguida só se o clima forçado também vier vazio —
        # decidido no hub após executar o clima.
        pass
    elif precisa_web and not tool_ok("consultar_clima"):
        extras.append(
            {
                "tool": "pesquisar_web",
                "params": {"query": f"{alvo} eleições notícias"},
                "motivo": "playbook_sem_clima_usa_web",
            }
        )
    return extras
