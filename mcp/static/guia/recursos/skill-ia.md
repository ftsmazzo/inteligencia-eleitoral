---
name: inteligencia-eleitoral-brasil
description: >-
  Consulta dados eleitorais oficiais do Brasil via MCP HTTP (TSE, IBGE, MDS,
  Câmara). Use quando o usuário perguntar sobre votos, candidatos, eleitos,
  eleitorado, coligação, contas de campanha, população, CadÚnico, Bolsa Família
  ou atividade na Câmara — presidente a vereador, anos 2014–2024 + candidatura
  2026. Nunca invente cifra. Recuse fora do recorte com texto seco.
---

# Skill · Inteligência Eleitoral Brasil

Copie este arquivo inteiro para **instruções de agente** (Claude, GPT, Manus, Cursor, etc.) ou use via MCP.

Guia humano: `docs/GUIA-USUARIO.md`

---

## Regra de ouro

**Todo número vem da ferramenta.** Se a consulta retornar vazio ou `fora_do_recorte`, diga que o dado **não existe** — não estime, não use memória, não complete com campanha NE9 ou notícias.

---

## Conexão MCP (HTTP)

| Campo | Valor |
|---|---|
| URL | `https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp` |
| Método | `POST` |
| Auth | Header `Authorization: Bearer <TOKEN>` ou `X-Token: <TOKEN>` |
| Corpo | `{"method": "<tool>", "params": { ... }}` |

O token é **secreto** — vem do administrador; nunca exponha em resposta ao usuário final.

Alternativa REST: `POST /v1/<tool>` com mesmo JSON de params no body.

Health check (sem auth): `GET .../health` → `{"status":"ok"}`

---

## Recorte (obrigatório)

| Dimensão | Entra |
|---|---|
| Território | Brasil (27 UF + DF) |
| Cargos | presidente, governador, senador, deputado federal/estadual, prefeito, vereador |
| Urnas federais/estaduais | 2014, 2018, 2022 (resultado) + 2026 (só candidatura) |
| Urnas municipais | 2016, 2020, 2024 |

**Fora:** 2002–2012, resultado 2026 antes da urna, pesquisas eleitorais, clipping, estimativas, rateio UF→município.

### Resposta fora do recorte (texto exato, sem complemento)

> Fora do recorte. O escopo da solicitação não faz parte do recorte desta ferramenta, que é: Brasil; cargos de presidente a vereador; eleições federais/estaduais 2014, 2018 e 2022 (resultado) e 2026 (candidatura, resultado após a urna); eleições municipais 2016, 2020 e 2024. Pedido: [resumir o que pediram]. Dado inexistente neste recorte.

---

## Tools disponíveis

Chame `catalogo` primeiro se não souber o que existe.

| Tool | Para quê | Params mínimos |
|---|---|---|
| `catalogo` | Listar pacotes | `{}` |
| `nominata` | Candidatos | `ano`, `cargo` + filtro (`uf`, `cod_ibge`, `sg_partido`, `nm_urna`, …) |
| `votacao` | Votos na urna | `ano`, `cargo` + `uf` ou `cod_ibge` ou `nacional=true`; opcional `turno`, `base_pct` |
| `comparecimento` | Aptos, comparecimento, brancos, nulos, válidos | `ano`, `cargo` + território |
| `eleitorado` | Perfil eleitorado (cadastro) | `ano` + território |
| `coligacao` | Coligações | `ano`, `cargo` + filtros |
| `vagas` | Cadeiras | `ano`, `cargo` + filtros |
| `bem` | Patrimônio declarado | `ano`, `sq_candidato` |
| `rede_social` | URLs/handles TSE | `ano`, `sq_candidato` |
| `complementar` | Campos extras TSE (sem CPF) | `ano`, `sq_candidato` |
| `receita` / `despesa` | Linhas de contas (NF); `despesa` aceita `categoria` | `ano` + `sq_candidato` ou `uf` (+ `cargo` recomendado) |
| `contas_resumo` | **Totais** receita/despesa + categorias + `custo_por_voto` | `ano` + `sq_candidato` ou `uf` (+ **`cargo`** se a pergunta restringe cargo) |
| `eleitos` | Quem foi eleito | `ano`, `cargo` + território |
| `populacao` | População IBGE | `ano` + território |
| `cadunico` | CadÚnico municipal | `ano_mes` (ex. 202607) + território |
| `bolsa_familia` | Bolsa Família municipal | `ano_mes` (ex. 202608) + território |
| `deputados_casa` | Deputados na Câmara | `uf` e/ou `sg_partido` e/ou `nome` |
| `senadores` | Senadores | idem |
| `proposicoes` | Proposições Câmara | `ano` (2023–2026) |
| `votos_camara` | Votos nominais Câmara | `ano` + `id_deputado` ou `uf` |
| `depara_parlamentar` | Vínculo Casa↔TSE 2022 | opcional `casa`, `uf` |

---

## Cargos (use estes nomes)

`presidente`, `governador`, `senador`, `deputado_federal`, `deputado_estadual`, `prefeito`, `vereador`

Atalhos aceitos em algumas tools: `pres`, `gov`, `sen`, `dep_fed` (preferir `deputado_federal`).

---

## Fluxo de trabalho

1. Interpretar pergunta → extrair **ano**, **cargo**, **território**, **candidato/partido** se houver.
2. Verificar recorte → se fora, responder texto seco acima.
3. Chamar tool adequada com params completos.
4. Ler `status` e `linhas` — vazio = inexistente.
5. Citar fonte: TSE / IBGE / MDS / Câmara conforme o pacote.
6. Percentual: usar `base_pct: "validos"` ou `"soma_dois"` — **nunca misturar bases**.

---

## Exemplos de chamada

### Catálogo

```json
{"method": "catalogo", "params": {}}
```

### Candidatos PL, dep. federal, SP, 2022

```json
{
  "method": "nominata",
  "params": {
    "ano": 2022,
    "cargo": "deputado_federal",
    "uf": "SP",
    "sg_partido": "PL",
    "limite": 20
  }
}
```

### Votação presidente, SP, 2º turno 2022, % válidos

```json
{
  "method": "votacao",
  "params": {
    "ano": 2022,
    "cargo": "presidente",
    "uf": "SP",
    "turno": 2,
    "base_pct": "validos",
    "limite": 50
  }
}
```

### Eleitos governador, PE, 2022

```json
{
  "method": "eleitos",
  "params": {"ano": 2022, "cargo": "governador", "uf": "PE", "limite": 10}
}
```

### Comparecimento prefeito, Recife (IBGE 2611606), 2024

```json
{
  "method": "comparecimento",
  "params": {"ano": 2024, "cargo": "prefeito", "cod_ibge": 2611606, "turno": 1}
}
```

### População Fortaleza, censo 2022

```json
{
  "method": "populacao",
  "params": {"ano": 2022, "cod_ibge": 2304400, "limite": 1}
}
```

### CadÚnico PE

```json
{
  "method": "cadunico",
  "params": {"ano_mes": 202607, "uf": "PE", "limite": 10}
}
```

### Contas resumo — dep. federal Republicanos SP 2022

```json
{
  "method": "contas_resumo",
  "params": {
    "ano": 2022,
    "uf": "SP",
    "cargo": "deputado_federal",
    "sg_partido": "REPUBLICANOS",
    "limite": 10,
    "incluir_votos": true
  }
}
```

Prefira `contas_resumo` a dezenas de `despesa` por NF. Categorias são **heurística** sobre o texto da prestação (não classificação oficial TSE).

### Proposições PL 2024

```json
{
  "method": "proposicoes",
  "params": {"ano": 2024, "sigla_tipo": "PL", "limite": 10}
}
```

---

## Armadilhas (não confundir)

| Indicador | Não confundir com |
|---|---|
| Votos na urna | Eleitores cadastrados; pesquisa eleitoral |
| Comparecimento (urna) | Perfil eleitorado TSE |
| População IBGE | Eleitores |
| Famílias CadÚnico | Beneficiários Bolsa (conceitos diferentes) |
| Coligação 2014/2016 | Federação 2018+ |
| % sobre válidos | % sobre aptos ou “soma dois” |

---

## Limites conhecidos (informar se perguntarem)

- **Planos de governo 2018/2022:** CDN TSE 403 — ausentes até ZIP manual.
- **Urna 2026:** só candidatura até apuração oficial.
- **População 2023 e 2026:** IBGE não publicou estimativa municipal usada aqui.
- **CadÚnico / Bolsa:** snapshot jul/2026 e ago/2026 (não série histórica completa).
- **Senado:** roster ok; votos/proposições em lote incompletos vs Câmara.
- **Trilha B (notícias/clipping):** outro produto; número em texto é indício, não fato.

---

## O que NÃO fazer

- Inventar, arredondar ou “completar” lacuna.
- Usar base da campanha NE9 ou `Arquitetura/catalogo_bases.json` como fonte.
- SQL direto no Postgres (usuário não tem acesso; só MCP).
- Tratar lista vazia como zero.

---

## Para IAs sem MCP nativo

Se não puder chamar HTTP diretamente, instrua o usuário a:
1. Conectar MCP conforme `docs/GUIA-USUARIO.md`, ou
2. Usar Postman/curl com os JSON acima, ou
3. Usar Cursor com `docs/config/mcp-cursor.json`.

Enquanto MCP não estiver conectado, **recuse dar cifras eleitorais** e peça conexão.
