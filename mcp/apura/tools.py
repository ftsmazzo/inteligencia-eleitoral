"""Definições OpenAI-compatible das tools MCP para o orquestrador."""

MCP_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_catalogo",
            "description": "Lista pacotes e indicadores disponíveis na base.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_nominata",
            "description": "Candidatos inscritos (nominata).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "sg_partido": {"type": "string"},
                    "nm_urna": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano", "cargo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_votacao",
            "description": "Votos na urna por candidato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "turno": {"type": "integer", "default": 1},
                    "sg_partido": {"type": "string"},
                    "nm_urna": {"type": "string"},
                    "base_pct": {"type": "string", "enum": ["validos", "soma_dois"]},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano", "cargo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_comparecimento",
            "description": "Aptos, comparecimento, brancos, nulos e válidos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "turno": {"type": "integer", "default": 1},
                },
                "required": ["ano", "cargo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_eleitos",
            "description": (
                "Quem foi eleito. Aceita uf=UF (ex.: CE) ou região (Nordeste, Norte, Sudeste, Sul, Centro-Oeste). "
                "sg_partido é expandido automaticamente para siglas históricas equivalentes "
                "(ex.: PL inclui PR e PSL; MDB inclui PMDB). "
                "status=vazio significa zero eleitos no filtro, não ausência de base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {
                        "type": "string",
                        "description": "UF (CE) ou região (Nordeste). Região expande para todas as UFs.",
                    },
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "sg_partido": {
                        "type": "string",
                        "description": "Sigla pedida; a API inclui equivalentes históricas automaticamente.",
                    },
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano", "cargo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_populacao",
            "description": "População IBGE municipal/UF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_cadunico",
            "description": "Famílias CadÚnico municipal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "anomes": {"type": "integer", "description": "Ex.: 202607"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "limite": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_bolsa_familia",
            "description": "Bolsa Família municipal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "anomes": {"type": "integer", "description": "Ex.: 202608"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "limite": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_deputados_casa",
            "description": "Deputados na Câmara (mandato atual).",
            "parameters": {
                "type": "object",
                "properties": {
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "nome": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_acervo",
            "description": (
                "Acervo semântico (planos de governo, programas, notas TSE) com filtro temporal. "
                "Cifra no texto é pista, não fato. Use para programa/narrativa/compromisso."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "ano_eleicao": {"type": "integer"},
                    "tipo": {"type": "string", "description": "plano_governo|programa_partido|nota_tse|…"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "limite": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_clima",
            "description": (
                "Radar / clima livre: Google News RSS + Apify Instagram (sem trava de campanha). "
                "Obrigatório para Instagram/@conta, news, ‘o que está saindo’. "
                "canal=instagram usa Apify em qualquer @handle; canal=news usa RSS livre. "
                "Cada item: fonte, quando/data_hora, rotulo. url pode ser null (não cole url_raw). "
                "Passe q=nome ou handle sem @, canal (instagram|news|x…), "
                "janela_horas (24 ou 168). Sempre indício — não use como cifra eleitoral."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Alvo ou tema livre"},
                    "canal": {"type": "string", "description": "instagram|news|x|facebook|youtube|tiktok|site"},
                    "origem": {"type": "string", "description": "clima|oficial"},
                    "tipo": {"type": "string"},
                    "urgencia": {"type": "string"},
                    "janela_horas": {"type": "integer", "description": "24=dia, 168=semana"},
                    "campaign_id": {"type": "integer", "description": "Opcional"},
                    "limite": {"type": "integer", "default": 20},
                },
            },
        },
    },
]

TOOL_TO_MCP: dict[str, str] = {
    "consultar_catalogo": "catalogo",
    "consultar_nominata": "nominata",
    "consultar_votacao": "votacao",
    "consultar_comparecimento": "comparecimento",
    "consultar_eleitos": "eleitos",
    "consultar_populacao": "populacao",
    "consultar_cadunico": "cadunico",
    "consultar_bolsa_familia": "bolsa_familia",
    "consultar_deputados_casa": "deputados_casa",
    "consultar_acervo": "acervo",
    "consultar_clima": "clima",
}
