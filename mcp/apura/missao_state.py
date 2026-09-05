"""Estado de missão do Apura (protocolo Airy + perfil comportamental).

Persistido em dados_json das mensagens assistant e recarregado na sessão.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EtapaAiry(str, Enum):
    INATIVO = "inativo"
    BRIEFING_OBJETIVO = "briefing_objetivo"
    BRIEFING_ESTILO = "briefing_estilo"
    BRIEFING_PAPEL = "briefing_papel"
    BRIEFING_DETALHE = "briefing_detalhe"
    BRIEFING_REFS = "briefing_refs"
    MATRIZ = "matriz"
    TOPICO = "topico"
    COMPILACAO = "compilacao"


class PerfilComportamento(str, Enum):
    OPERACIONAL = "operacional"  # consultor_minimo
    ANALISTA = "analista"
    ESTRATEGISTA = "estrategista"  # + coordenador


_SLUG_MAP = {
    "consultor_minimo": PerfilComportamento.OPERACIONAL,
    "analista": PerfilComportamento.ANALISTA,
    "estrategista": PerfilComportamento.ESTRATEGISTA,
    "coordenador": PerfilComportamento.ESTRATEGISTA,
}

_CMD_OK = re.compile(r"^\s*ok\s*[.!]*\s*$", re.I)
_CMD_APROVADO = re.compile(r"^\s*aprovado\s*[.!]*\s*$", re.I)
_CMD_ENVIADO = re.compile(r"^\s*enviado\s*[.!]*\s*$", re.I)
_CMD_CONCLUIDO = re.compile(r"^\s*conclu[ií]do\s*[.!]*\s*$", re.I)
_CMD_ATIVAR = re.compile(
    r"ativar\s+(?:protocolo\s+)?ar[iy](?:\s+eleitoral)?",
    re.I,
)
_CMD_ADD_MATRIZ = re.compile(r"adicionar\s+a\s+matriz", re.I)
_CMD_LEMBRETE = re.compile(r"ar[iy],?\s*lembrete\s+de\s+protocolo", re.I)
_CMD_CRIACAO = re.compile(
    r"ativar\s+ar[iy]\s+cria[cç][aã]o|modo\s+cria[cç][aã]o|pack\s+cria[cç][aã]o",
    re.I,
)


@dataclass
class MissaoState:
    perfil: str = PerfilComportamento.ANALISTA.value
    protocolo_ativo: bool = False
    pack_criacao: bool = False
    etapa: str = EtapaAiry.INATIVO.value
    aguardando_ok: bool = False
    objetivo: str = ""
    estilo: str = ""
    papel: str = ""
    detalhe: str = ""
    referencias: list[str] = field(default_factory=list)
    matriz: list[str] = field(default_factory=list)
    topico_idx: int = 0
    aprovados: dict[str, str] = field(default_factory=dict)
    agentes_plano: list[str] = field(default_factory=list)
    ultima_atualizacao: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MissaoState:
        if not data or not isinstance(data, dict):
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        if "referencias" in kwargs and not isinstance(kwargs["referencias"], list):
            kwargs["referencias"] = []
        if "matriz" in kwargs and not isinstance(kwargs["matriz"], list):
            kwargs["matriz"] = []
        if "aprovados" in kwargs and not isinstance(kwargs["aprovados"], dict):
            kwargs["aprovados"] = {}
        if "agentes_plano" in kwargs and not isinstance(kwargs["agentes_plano"], list):
            kwargs["agentes_plano"] = []
        return cls(**kwargs)

    @property
    def usa_protocolo_airy(self) -> bool:
        return self.perfil == PerfilComportamento.ESTRATEGISTA.value and self.protocolo_ativo

    @property
    def caminho_curto(self) -> bool:
        return self.perfil == PerfilComportamento.OPERACIONAL.value


def perfil_de_slug(slug: str | None) -> PerfilComportamento:
    if not slug:
        return PerfilComportamento.ANALISTA
    return _SLUG_MAP.get(slug, PerfilComportamento.ANALISTA)


def estado_inicial(perfil_slug: str | None) -> MissaoState:
    comp = perfil_de_slug(perfil_slug)
    return MissaoState(perfil=comp.value)


def carregar_do_historico_dados(
    dados_anteriores: list[dict[str, Any] | None],
    *,
    perfil_slug: str | None,
) -> MissaoState:
    """Recupera o último missao_state gravado; senão inicia pelo perfil do vínculo."""
    for d in reversed(dados_anteriores):
        if isinstance(d, dict) and isinstance(d.get("missao_state"), dict):
            st = MissaoState.from_dict(d["missao_state"])
            # Perfil do vínculo manda (login); estado de etapa persiste
            st.perfil = perfil_de_slug(perfil_slug).value
            return st
    return estado_inicial(perfil_slug)


def detectar_comando(mensagem: str) -> str | None:
    t = (mensagem or "").strip()
    if not t:
        return None
    if _CMD_LEMBRETE.search(t):
        return "lembrete"
    if _CMD_CRIACAO.search(t):
        return "ativar_criacao"
    if _CMD_ATIVAR.search(t):
        return "ativar"
    if _CMD_ADD_MATRIZ.search(t):
        return "adicionar_matriz"
    if _CMD_CONCLUIDO.match(t):
        return "concluido"
    if _CMD_APROVADO.match(t):
        return "aprovado"
    if _CMD_ENVIADO.match(t):
        return "enviado"
    if _CMD_OK.match(t):
        return "ok"
    return None


_ORDEM_BRIEFING = [
    EtapaAiry.BRIEFING_OBJETIVO,
    EtapaAiry.BRIEFING_ESTILO,
    EtapaAiry.BRIEFING_PAPEL,
    EtapaAiry.BRIEFING_DETALHE,
    EtapaAiry.BRIEFING_REFS,
]


def aplicar_comando(state: MissaoState, comando: str | None, mensagem: str) -> MissaoState:
    """Avança a máquina de estados Airy. Só age se perfil estrategista."""
    if state.perfil != PerfilComportamento.ESTRATEGISTA.value:
        return state

    if comando == "ativar":
        state.protocolo_ativo = True
        state.pack_criacao = False
        state.etapa = EtapaAiry.BRIEFING_OBJETIVO.value
        state.aguardando_ok = False
        state.ultima_atualizacao = "protocolo_ativado"
        return state

    if comando == "ativar_criacao":
        state.protocolo_ativo = True
        state.pack_criacao = True
        state.etapa = EtapaAiry.BRIEFING_OBJETIVO.value
        state.aguardando_ok = False
        state.ultima_atualizacao = "pack_criacao"
        return state

    if comando == "lembrete":
        state.ultima_atualizacao = "lembrete"
        return state

    if not state.protocolo_ativo:
        return state

    etapa = EtapaAiry(state.etapa) if state.etapa in EtapaAiry._value2member_map_ else EtapaAiry.INATIVO

    if comando == "ok" and state.aguardando_ok:
        state.aguardando_ok = False
        if etapa in _ORDEM_BRIEFING:
            idx = _ORDEM_BRIEFING.index(etapa)
            if idx + 1 < len(_ORDEM_BRIEFING):
                state.etapa = _ORDEM_BRIEFING[idx + 1].value
            else:
                state.etapa = EtapaAiry.MATRIZ.value
        elif etapa == EtapaAiry.MATRIZ:
            state.etapa = EtapaAiry.TOPICO.value
            state.topico_idx = 0
        elif etapa == EtapaAiry.COMPILACAO:
            state.etapa = EtapaAiry.INATIVO.value
            state.protocolo_ativo = False
        state.ultima_atualizacao = f"ok→{state.etapa}"
        return state

    if comando == "enviado" and etapa == EtapaAiry.BRIEFING_REFS:
        state.aguardando_ok = True
        state.ultima_atualizacao = "refs_enviadas"
        return state

    if comando == "aprovado" and etapa == EtapaAiry.TOPICO:
        key = f"topico_{state.topico_idx + 1}"
        state.aprovados[key] = state.aprovados.get("_rascunho", "")
        state.aprovados.pop("_rascunho", None)
        if state.topico_idx + 1 < len(state.matriz):
            state.topico_idx += 1
        state.ultima_atualizacao = f"aprovado_{key}"
        return state

    if comando == "concluido":
        state.etapa = EtapaAiry.COMPILACAO.value
        state.aguardando_ok = True
        state.ultima_atualizacao = "compilacao"
        return state

    if comando == "adicionar_matriz":
        state.etapa = EtapaAiry.MATRIZ.value
        state.aguardando_ok = True
        state.ultima_atualizacao = "add_matriz"
        return state

    # Conteúdo livre: preenche campos do briefing e pede OK
    if etapa == EtapaAiry.BRIEFING_OBJETIVO and not comando:
        state.objetivo = mensagem.strip()[:4000]
        state.aguardando_ok = True
    elif etapa == EtapaAiry.BRIEFING_ESTILO and not comando:
        state.estilo = mensagem.strip()[:1000]
        state.aguardando_ok = True
    elif etapa == EtapaAiry.BRIEFING_PAPEL and not comando:
        state.papel = mensagem.strip()[:1000]
        state.aguardando_ok = True
    elif etapa == EtapaAiry.BRIEFING_DETALHE and not comando:
        state.detalhe = mensagem.strip()[:8000]
        state.aguardando_ok = True
    elif etapa == EtapaAiry.BRIEFING_REFS and not comando:
        state.referencias.append(mensagem.strip()[:2000])
    elif etapa == EtapaAiry.MATRIZ and not comando and not state.aguardando_ok:
        # Usuário pode colar ajustes; matriz é montada pelo redator e confirmada com OK
        state.aguardando_ok = True
    elif etapa == EtapaAiry.TOPICO and not comando:
        state.aprovados["_rascunho"] = mensagem.strip()[:12000]

    return state


def resumo_para_prompt(state: MissaoState) -> str:
    if state.caminho_curto:
        return (
            "PERFIL_COMPORTAMENTO: operacional\n"
            "Modo: respostas curtas, resumo, contatos e tarefas. Sem protocolo Ary."
        )
    if state.perfil == PerfilComportamento.ANALISTA.value:
        return (
            "PERFIL_COMPORTAMENTO: analista\n"
            "Modo: inteligência com cifra + leitura. War-room curto. Sem Matriz Ary."
        )
    linhas = [
        "PERFIL_COMPORTAMENTO: estrategista",
        f"protocolo_ary: {'ATIVO' if state.protocolo_ativo else 'em espera (diga Ativar Ary)'}",
        f"pack_criacao: {state.pack_criacao}",
        f"etapa: {state.etapa}",
        f"aguardando_ok: {state.aguardando_ok}",
    ]
    if state.objetivo:
        linhas.append(f"objetivo: {state.objetivo[:800]}")
    if state.estilo:
        linhas.append(f"estilo: {state.estilo[:400]}")
    if state.papel:
        linhas.append(f"papel: {state.papel[:400]}")
    if state.detalhe:
        linhas.append(f"detalhe: {state.detalhe[:1200]}")
    if state.matriz:
        linhas.append("matriz: " + " | ".join(state.matriz[:20]))
    if state.agentes_plano:
        linhas.append("agentes_plano: " + ", ".join(state.agentes_plano))
    return "\n".join(linhas)
