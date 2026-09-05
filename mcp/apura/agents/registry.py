"""Registry de agentes lógicos → conjuntos de tools."""

from __future__ import annotations

AGENTE_DADOS = "dados"
AGENTE_CLIMA = "clima"
AGENTE_ACERVO = "acervo"
AGENTE_WEB = "web"
AGENTE_MEDIA = "media"
AGENTE_VISUAL = "visual"
AGENTE_OPERACIONAL = "operacional"

TOOLS_DADOS = frozenset(
    {
        "consultar_catalogo",
        "consultar_municipio",
        "consultar_nominata",
        "consultar_votacao",
        "consultar_comparecimento",
        "consultar_eleitorado",
        "consultar_coligacao",
        "consultar_vagas",
        "consultar_bem",
        "consultar_rede_social",
        "consultar_complementar",
        "consultar_receita",
        "consultar_despesa",
        "consultar_contas_resumo",
        "consultar_eleitos",
        "consultar_populacao",
        "consultar_cadunico",
        "consultar_bolsa_familia",
        "consultar_deputados_casa",
        "consultar_senadores",
        "consultar_proposicoes",
        "consultar_votos_camara",
        "consultar_depara_parlamentar",
        "consultar_linha_temporal",
        "consultar_cruzamento_social",
        "consultar_mandato_urna",
    }
)

TOOLS_CLIMA = frozenset({"consultar_clima"})
TOOLS_ACERVO = frozenset({"consultar_acervo", "consultar_acervo_comparar"})
TOOLS_WEB = frozenset({"pesquisar_web"})
TOOLS_MEDIA = frozenset({"ler_pdf", "ler_imagem", "transcrever_audio"})
TOOLS_VISUAL = frozenset({"gerar_imagem", "gerar_mapa_html"})
TOOLS_OPERACIONAL = frozenset({"operacional_contato", "operacional_tarefa"})

AGENTE_POR_TOOL: dict[str, str] = {}
for _name, _agent in (
    *[(t, AGENTE_DADOS) for t in TOOLS_DADOS],
    *[(t, AGENTE_CLIMA) for t in TOOLS_CLIMA],
    *[(t, AGENTE_ACERVO) for t in TOOLS_ACERVO],
    *[(t, AGENTE_WEB) for t in TOOLS_WEB],
    *[(t, AGENTE_MEDIA) for t in TOOLS_MEDIA],
    *[(t, AGENTE_VISUAL) for t in TOOLS_VISUAL],
    *[(t, AGENTE_OPERACIONAL) for t in TOOLS_OPERACIONAL],
):
    AGENTE_POR_TOOL[_name] = _agent

CAMADA_POR_AGENTE = {
    AGENTE_DADOS: "fato",
    AGENTE_ACERVO: "acervo",
    AGENTE_CLIMA: "indicio_clima",
    AGENTE_WEB: "indicio_web",
    AGENTE_MEDIA: "indicio_media",
    AGENTE_VISUAL: "artefato_visual",
    AGENTE_OPERACIONAL: "operacional",
}


def agente_da_tool(tool_name: str) -> str:
    return AGENTE_POR_TOOL.get(tool_name, "dados")


def camada_da_tool(tool_name: str) -> str:
    return CAMADA_POR_AGENTE.get(agente_da_tool(tool_name), "fato")


def plano_de_tool_log(tool_log: list[dict]) -> list[str]:
    seen: list[str] = []
    for tr in tool_log:
        a = agente_da_tool(tr.get("tool") or "")
        if a not in seen:
            seen.append(a)
    return seen
