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
            "name": "consultar_eleitorado",
            "description": "Perfil do eleitorado (sexo, faixa, escolaridade) por município/UF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "nacional": {"type": "boolean"},
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_coligacao",
            "description": "Coligações e federações por ano/cargo (quebra 2014 ≠ 2018+).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
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
            "name": "consultar_vagas",
            "description": "Vagas disputadas por cargo/UF/município.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano", "cargo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_bem",
            "description": "Patrimônio declarado (bens) de candidato por sq_candidato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano", "sq_candidato"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_receita",
            "description": "Receitas de campanha (prestação TSE). Ordenação: maior valor primeiro. Consulta por UF retorna só linhas com candidato (sq_candidato); use cargo para filtrar governador etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "cargo": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_despesa",
            "description": "Despesas de campanha (prestação TSE). Ordenação: maior valor primeiro. Consulta por UF retorna só linhas com candidato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "cargo": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_eleitos",
            "description": (
                "Quem foi eleito. Aceita uf=UF ou região (Nordeste…). "
                "sg_partido expande siglas históricas (PL↔PSL, MDB↔PMDB)."
            ),
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
            "description": "População IBGE municipal/UF (censo ou estimativa).",
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
            "description": "Famílias CadÚnico municipal (MDS).",
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
            "description": "Bolsa Família municipal (MDS).",
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
            "description": "Deputados na Câmara (mandato atual L57).",
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
            "name": "consultar_senadores",
            "description": "Senadores em exercício (lista atual ou legislatura).",
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
            "name": "consultar_proposicoes",
            "description": "Proposições na Câmara por ano e deputado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sigla_tipo": {"type": "string"},
                    "id_deputado": {"type": "integer"},
                    "limite": {"type": "integer", "default": 50},
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_votos_camara",
            "description": "Votos nominais de deputado na Câmara.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "id_deputado": {"type": "integer"},
                    "uf": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_depara_parlamentar",
            "description": "De-para urna TSE ↔ id Câmara/Senado por ano de eleição.",
            "parameters": {
                "type": "object",
                "properties": {
                    "casa": {"type": "string", "description": "camara|senado"},
                    "ano_eleicao": {"type": "integer", "default": 2022},
                    "uf": {"type": "string"},
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
                "Acervo semântico: planos de governo, fichas territoriais, notas TSE. "
                "Para candidato: query=tema, ano_eleicao, tipo=plano_governo, nm_candidato. "
                "Cifra no texto é pista, não fato."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "ano_eleicao": {"type": "integer"},
                    "tipo": {"type": "string", "description": "plano_governo|ficha_territorial|nota_tse|programa_partido"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "nm_candidato": {"type": "string"},
                    "limite": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_acervo_comparar",
            "description": (
                "Compara o mesmo tema em dois anos de acervo (ex.: segurança 2022 vs 2026). "
                "Use nm_candidato quando comparar planos de pessoas diferentes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "ano_a": {"type": "integer"},
                    "ano_b": {"type": "integer"},
                    "tipo": {"type": "string", "default": "plano_governo"},
                    "nm_candidato": {"type": "string"},
                    "limite": {"type": "integer", "default": 5},
                },
                "required": ["query", "ano_a", "ano_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_clima",
            "description": (
                "Clima livre: Google News RSS + Apify Instagram. "
                "canal=instagram|news. Sempre indício — não use como cifra."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "canal": {"type": "string"},
                    "origem": {"type": "string"},
                    "tipo": {"type": "string"},
                    "janela_horas": {"type": "integer", "description": "24 ou 168"},
                    "campaign_id": {"type": "integer"},
                    "limite": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_linha_temporal",
            "description": (
                "Série de eleitos do mesmo partido em vários anos (ex.: PL deputado federal Nordeste 2014/2018/2022)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cargo": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "uf": {"type": "string"},
                    "anos": {"type": "array", "items": {"type": "integer"}},
                    "limite": {"type": "integer", "default": 200},
                },
                "required": ["cargo", "sg_partido"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_cruzamento_social",
            "description": (
                "Top municípios por CadÚnico ou Bolsa Família cruzados com eleito na urna. "
                "Requer uf. Não inferir causalidade."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano_urna": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "indicador": {"type": "string", "enum": ["cadunico", "bolsa_familia"], "default": "cadunico"},
                    "anomes": {"type": "integer"},
                    "uf": {"type": "string"},
                    "top_n": {"type": "integer", "default": 15},
                },
                "required": ["ano_urna", "cargo", "uf"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_mandato_urna",
            "description": (
                "Deputados na Câmara (mandato) com contagem de proposições; "
                "cruzamento com de-para da urna 2022."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano_eleicao": {"type": "integer", "default": 2022},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "tema": {"type": "string", "description": "Filtro em ementa/indexação"},
                    "limite": {"type": "integer", "default": 30},
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
    "consultar_eleitorado": "eleitorado",
    "consultar_coligacao": "coligacao",
    "consultar_vagas": "vagas",
    "consultar_bem": "bem",
    "consultar_receita": "receita",
    "consultar_despesa": "despesa",
    "consultar_eleitos": "eleitos",
    "consultar_populacao": "populacao",
    "consultar_cadunico": "cadunico",
    "consultar_bolsa_familia": "bolsa_familia",
    "consultar_deputados_casa": "deputados_casa",
    "consultar_senadores": "senadores",
    "consultar_proposicoes": "proposicoes",
    "consultar_votos_camara": "votos_camara",
    "consultar_depara_parlamentar": "depara_parlamentar",
    "consultar_acervo": "acervo",
    "consultar_acervo_comparar": "acervo_comparar",
    "consultar_clima": "clima",
    "consultar_linha_temporal": "linha_temporal",
    "consultar_cruzamento_social": "cruzamento_social",
    "consultar_mandato_urna": "mandato_urna",
}
