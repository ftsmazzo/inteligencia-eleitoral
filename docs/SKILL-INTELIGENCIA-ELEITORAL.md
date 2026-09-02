---
name: inteligencia-eleitoral-brasil
description: >-
  Consulta dados eleitorais oficiais do Brasil via MCP HTTP (TSE, IBGE, MDS,
  CÃ¢mara). Use quando o usuÃ¡rio perguntar sobre votos, candidatos, eleitos,
  eleitorado, coligaÃ§Ã£o, contas de campanha, populaÃ§Ã£o, CadÃšnico, Bolsa FamÃ­lia
  ou atividade na CÃ¢mara â€” presidente a vereador, anos 2014â€“2024 + candidatura
  2026. Nunca invente cifra. Recuse fora do recorte com texto seco.
---

# Skill Â· InteligÃªncia Eleitoral Brasil

Copie este arquivo inteiro para **instruÃ§Ãµes de agente** (Claude, GPT, Manus, Cursor, etc.) ou use via MCP.

Guia humano: `docs/GUIA-USUARIO.md`

---

## Regra de ouro

**Todo nÃºmero vem da ferramenta.** Se a consulta retornar vazio ou `fora_do_recorte`, diga que o dado **nÃ£o existe** â€” nÃ£o estime, nÃ£o use memÃ³ria, nÃ£o complete com campanha NE9 ou notÃ­cias.

---

## ConexÃ£o MCP (HTTP)

| Campo | Valor |
|---|---|
| URL | `https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp` |
| MÃ©todo | `POST` |
| Auth | Header `Authorization: Bearer <TOKEN>` ou `X-Token: <TOKEN>` |
| Corpo | `{"method": "<tool>", "params": { ... }}` |

O token Ã© **secreto** â€” vem do administrador; nunca exponha em resposta ao usuÃ¡rio final.

Alternativa REST: `POST /v1/<tool>` com mesmo JSON de params no body.

Health check (sem auth): `GET .../health` â†’ `{"status":"ok"}`

---

## Recorte (obrigatÃ³rio)

| DimensÃ£o | Entra |
|---|---|
| TerritÃ³rio | Brasil (27 UF + DF) |
| Cargos | presidente, governador, senador, deputado federal/estadual, prefeito, vereador |
| Urnas federais/estaduais | 2014, 2018, 2022 (resultado) + 2026 (sÃ³ candidatura) |
| Urnas municipais | 2016, 2020, 2024 |

**Fora:** 2002â€“2012, resultado 2026 antes da urna, pesquisas eleitorais, clipping, estimativas, rateio UFâ†’municÃ­pio.

### Resposta fora do recorte (texto exato, sem complemento)

> Fora do recorte. O escopo da solicitaÃ§Ã£o nÃ£o faz parte do recorte desta ferramenta, que Ã©: Brasil; cargos de presidente a vereador; eleiÃ§Ãµes federais/estaduais 2014, 2018 e 2022 (resultado) e 2026 (candidatura, resultado apÃ³s a urna); eleiÃ§Ãµes municipais 2016, 2020 e 2024. Pedido: [resumir o que pediram]. Dado inexistente neste recorte.

---

## Tools disponÃ­veis

Chame `catalogo` primeiro se nÃ£o souber o que existe.

| Tool | Para quÃª | Params mÃ­nimos |
|---|---|---|
| `catalogo` | Listar pacotes | `{}` |
| `nominata` | Candidatos | `ano`, `cargo` + filtro (`uf`, `cod_ibge`, `sg_partido`, `nm_urna`, â€¦) |
| `votacao` | Votos na urna | `ano`, `cargo` + `uf` ou `cod_ibge` ou `nacional=true`; opcional `turno`, `base_pct` |
| `comparecimento` | Aptos, comparecimento, brancos, nulos, vÃ¡lidos | `ano`, `cargo` + territÃ³rio |
| `eleitorado` | Perfil eleitorado (cadastro) | `ano` + territÃ³rio |
| `coligacao` | ColigaÃ§Ãµes | `ano`, `cargo` + filtros |
| `vagas` | Cadeiras | `ano`, `cargo` + filtros |
| `bem` | PatrimÃ´nio declarado | `ano`, `sq_candidato` |
| `rede_social` | URLs/handles TSE | `ano`, `sq_candidato` |
| `complementar` | Campos extras TSE (sem CPF) | `ano`, `sq_candidato` |
| `receita` / `despesa` | Linhas de contas (NF); `despesa` aceita `categoria` | `ano` + `sq_candidato` ou `uf` (+ `cargo` recomendado) |
| `contas_resumo` | **Totais** receita/despesa + categorias + `custo_por_voto` | `ano` + `sq_candidato` ou `uf` (+ **`cargo`** se a pergunta restringe cargo) |
| `eleitos` | Quem foi eleito | `ano`, `cargo` + territÃ³rio |
| `populacao` | PopulaÃ§Ã£o IBGE | `ano` + territÃ³rio |
| `cadunico` | CadÃšnico municipal | `ano_mes` (ex. 202607) + territÃ³rio |
| `bolsa_familia` | Bolsa FamÃ­lia municipal | `ano_mes` (ex. 202608) + territÃ³rio |
| `deputados_casa` | Deputados na CÃ¢mara | `uf` e/ou `sg_partido` e/ou `nome` |
| `senadores` | Senadores | idem |
| `proposicoes` | ProposiÃ§Ãµes CÃ¢mara | `ano` (2023â€“2026) |
| `votos_camara` | Votos nominais CÃ¢mara | `ano` + `id_deputado` ou `uf` |
| `depara_parlamentar` | VÃ­nculo Casaâ†”TSE 2022 | opcional `casa`, `uf` |

---

## Cargos (use estes nomes)

`presidente`, `governador`, `senador`, `deputado_federal`, `deputado_estadual`, `prefeito`, `vereador`

Atalhos aceitos em algumas tools: `pres`, `gov`, `sen`, `dep_fed` (preferir `deputado_federal`).

---

## Fluxo de trabalho

1. Interpretar pergunta â†’ extrair **ano**, **cargo**, **territÃ³rio**, **candidato/partido** se houver.
2. Verificar recorte â†’ se fora, responder texto seco acima.
3. Chamar tool adequada com params completos.
4. Ler `status` e `linhas` â€” vazio = inexistente.
5. Citar fonte: TSE / IBGE / MDS / CÃ¢mara conforme o pacote.
6. Percentual: usar `base_pct: "validos"` ou `"soma_dois"` â€” **nunca misturar bases**.

---

## Exemplos de chamada

### CatÃ¡logo

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

### VotaÃ§Ã£o presidente, SP, 2Âº turno 2022, % vÃ¡lidos

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

### PopulaÃ§Ã£o Fortaleza, censo 2022

```json
{
  "method": "populacao",
  "params": {"ano": 2022, "cod_ibge": 2304400, "limite": 1}
}
```

### CadÃšnico PE

```json
{
  "method": "cadunico",
  "params": {"ano_mes": 202607, "uf": "PE", "limite": 10}
}
```

### Contas resumo â€” dep. federal Republicanos SP 2022

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

Prefira `contas_resumo` a dezenas de `despesa` por NF. Categorias sÃ£o **heurÃ­stica** sobre o texto da prestaÃ§Ã£o (nÃ£o classificaÃ§Ã£o oficial TSE).

### ProposiÃ§Ãµes PL 2024

```json
{
  "method": "proposicoes",
  "params": {"ano": 2024, "sigla_tipo": "PL", "limite": 10}
}
```

---

## Armadilhas (nÃ£o confundir)

| Indicador | NÃ£o confundir com |
|---|---|
| Votos na urna | Eleitores cadastrados; pesquisa eleitoral |
| Comparecimento (urna) | Perfil eleitorado TSE |
| PopulaÃ§Ã£o IBGE | Eleitores |
| FamÃ­lias CadÃšnico | BeneficiÃ¡rios Bolsa (conceitos diferentes) |
| ColigaÃ§Ã£o 2014/2016 | FederaÃ§Ã£o 2018+ |
| % sobre vÃ¡lidos | % sobre aptos ou â€œsoma doisâ€ |

---

## Limites conhecidos (informar se perguntarem)

- **Planos de governo 2018/2022:** CDN TSE 403 â€” ausentes atÃ© ZIP manual.
- **Urna 2026:** sÃ³ candidatura atÃ© apuraÃ§Ã£o oficial.
- **PopulaÃ§Ã£o 2023 e 2026:** IBGE nÃ£o publicou estimativa municipal usada aqui.
- **CadÃšnico / Bolsa:** snapshot jul/2026 e ago/2026 (nÃ£o sÃ©rie histÃ³rica completa).
- **Senado:** roster ok; votos/proposiÃ§Ãµes em lote incompletos vs CÃ¢mara.
- **Trilha B (notÃ­cias/clipping):** outro produto; nÃºmero em texto Ã© indÃ­cio, nÃ£o fato.

---

## O que NÃƒO fazer

- Inventar, arredondar ou â€œcompletarâ€ lacuna.
- Usar base da campanha NE9 ou `Arquitetura/catalogo_bases.json` como fonte.
- SQL direto no Postgres (usuÃ¡rio nÃ£o tem acesso; sÃ³ MCP).
- Tratar lista vazia como zero.

---

## Para IAs sem MCP nativo

Se nÃ£o puder chamar HTTP diretamente, instrua o usuÃ¡rio a:
1. Conectar MCP conforme `docs/GUIA-USUARIO.md`, ou
2. Usar Postman/curl com os JSON acima, ou
3. Usar Cursor com `docs/config/mcp-cursor.json`.

Enquanto MCP nÃ£o estiver conectado, **recuse dar cifras eleitorais** e peÃ§a conexÃ£o.
