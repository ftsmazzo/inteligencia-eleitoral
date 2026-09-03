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
            "name": "consultar_municipio",
            "description": (
                "Resolve nome de município → cod_ibge (e cd_municipio_tse). "
                "Chame ANTES de votacao/comparecimento/eleitorado/populacao/prefeito/vereador "
                "quando o usuário citar cidade pelo nome (ex. Taubaté, Recife). Passe uf se souber."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "uf": {"type": "string"},
                    "limite": {"type": "integer", "default": 10},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_nominata",
            "description": (
                "Candidatos inscritos (chapa). Geografia = território de INSCRIÇÃO: "
                "presidente/gov/senador/dep.federal/dep.estadual → UF (município NÃO filtra a lista); "
                "prefeito/vereador → cod_ibge (obtenha via consultar_municipio). "
                "2026 = só candidatura (sem votos)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "cargo": {"type": "string"},
                    "uf": {"type": "string"},
                    "cod_ibge": {"type": "integer"},
                    "sg_partido": {"type": "string"},
                    "nr_candidato": {"type": "integer"},
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
            "description": (
                "Votos na urna. Geografia = ONDE o eleitor votou: "
                "cod_ibge do município é válido para QUALQUER cargo "
                "(ex. votos a presidente/dep.federal/senador EM Taubaté). "
                "Também aceita uf ou nacional=true. Resolve cidade com consultar_municipio."
            ),
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
            "description": (
                "Aptos, comparecimento, brancos, nulos e válidos. "
                "Aceita cod_ibge (cidade) ou uf/nacional — para qualquer cargo."
            ),
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
            "name": "consultar_rede_social",
            "description": (
                "URLs/handles declarados ao TSE (cadastro do candidato), NÃO o feed de posts. "
                "Para resumir o que rolou no Instagram use consultar_clima canal=instagram. "
                "Exige ano+sq_candidato. Anos: 2020/2022/2024/2026."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "limite": {"type": "integer", "default": 20},
                },
                "required": ["ano", "sq_candidato"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_complementar",
            "description": (
                "Informações complementares TSE (reeleição, teto de gastos, situação pleito/urna, etc.). "
                "Exige ano+sq_candidato. Sem CPF."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
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
            "description": (
                "Linhas de despesa (NF/prestação TSE). Preferir consultar_contas_resumo para totais. "
                "categoria opcional: publicidade|eventos|juridico|pessoal|logistica|estrutura|outros."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "cargo": {"type": "string"},
                    "limite": {"type": "integer", "default": 50},
                    "categoria": {
                        "type": "string",
                        "description": "publicidade|eventos|juridico|pessoal|logistica|estrutura|outros",
                    },
                },
                "required": ["ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_contas_resumo",
            "description": (
                "Totais de receita/despesa por candidato + breakdown por categoria + qt_votos e custo_por_voto. "
                "Use para ranking de gasto e gasto×voto (não liste NFs). Exige ano e (sq_candidato ou uf); "
                "passe cargo quando a pergunta restringe cargo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ano": {"type": "integer"},
                    "sq_candidato": {"type": "integer"},
                    "uf": {"type": "string"},
                    "sg_partido": {"type": "string"},
                    "cargo": {"type": "string"},
                    "limite": {"type": "integer", "default": 30},
                    "incluir_votos": {"type": "boolean", "default": True},
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
                "Acervo semântico: planos, fichas territoriais, notas TSE, glossário e playbooks. "
                "Tema/estratégia: tipo=playbook_estrategia ou glossario. "
                "Para candidato: query=tema, ano_eleicao, tipo=plano_governo, nm_candidato. "
                "Cifra no texto é pista, não fato."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "ano_eleicao": {"type": "integer"},
                    "tipo": {
                        "type": "string",
                        "description": (
                            "plano_governo|ficha_territorial|nota_tse|programa_partido|"
                            "glossario|playbook_estrategia"
                        ),
                    },
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
                "Clima livre: primeiro tenta o que o Radar já coletou desta campanha, senão cai pra "
                "Google News RSS (canal=news) ou Apify Instagram (canal=instagram). Sempre indício — "
                "não use como cifra. Se a pergunta citar @handle ou 'instagram de X', chame com "
                "canal=instagram e q=handle (sem @) NA HORA, sem perguntar período/tipo antes — use "
                "janela_horas=168 como padrão se não for dito outro. Vazio é uma resposta válida "
                "(SEM cobertura ainda), não um erro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "canal": {"type": "string"},
                    "origem": {"type": "string"},
                    "tipo": {"type": "string"},
                    "janela_horas": {"type": "integer", "description": "24 ou 168 (padrão 168 se omitido)"},
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
    "consultar_municipio": "municipio",
    "consultar_nominata": "nominata",
    "consultar_votacao": "votacao",
    "consultar_comparecimento": "comparecimento",
    "consultar_eleitorado": "eleitorado",
    "consultar_coligacao": "coligacao",
    "consultar_vagas": "vagas",
    "consultar_bem": "bem",
    "consultar_rede_social": "rede_social",
    "consultar_complementar": "complementar",
    "consultar_receita": "receita",
    "consultar_despesa": "despesa",
    "consultar_contas_resumo": "contas_resumo",
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
