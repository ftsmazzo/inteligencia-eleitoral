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
            "description": "Quem foi eleito.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                    "sg_partido": {"type": "string"},
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
}
