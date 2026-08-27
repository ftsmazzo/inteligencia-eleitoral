# Entrega MCP · Inteligência Eleitoral Brasil

Versão 0.1 · 26/08/2026

**Guia do usuário (página web):** https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/guia  
**Skill para IAs:** download na página /guia ou `docs/SKILL-INTELIGENCIA-ELEITORAL.md`

A pessoa designada **não recebe login do Postgres**. Acesso só via HTTP(S) com token.

## Endpoints

| Uso | URL |
|---|---|
| Health | `https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/health` |
| MCP (JSON) | `POST …/mcp` |
| REST fino | `POST …/v1/<tool>` (mesmo contrato) |

## Autenticação

Header **um** dos dois:

```http
Authorization: Bearer <MCP_TOKEN>
```

```http
X-Token: <MCP_TOKEN>
```

O valor de `MCP_TOKEN` está no EasyPanel (serviço **mcp-api** → Environment) e no `.env` local da equipe técnica. **Nunca** commitar nem colar o token em chat.

## Recorte (resumo)

Brasil · presidente a vereador · federais 2014/2018/2022 (+2026 candidatura) · municipais 2016/2020/2024.  
Fora do recorte: resposta seca (`docs/SPEC-BRASIL.md`). Sem estimativa.

## Tools disponíveis

`catalogo`, `nominata`, `votacao`, `comparecimento`, `eleitorado`, `coligacao`, `vagas`, `bem`, `receita`, `despesa`, `eleitos`, `populacao`, `cadunico`, `bolsa_familia`, `deputados_casa`, `senadores`, `proposicoes`, `votos_camara`, `depara_parlamentar`, `acervo`, `clima`.

- **acervo** — Trilha B (planos/programas/notas com vigência). Cifra no texto = pista.
- **clima** — Radar sob demanda (`q`, `canal`, `janela_horas`). Sempre `nivel=indicio`. Não exige candidato pré-configurado.

## Exemplos MCP (`POST /mcp`)

Corpo: `{ "method": "<tool>", "params": { … } }`

**Cargos:** use `deputado_federal`, não `dep_federal`.

### 1. Catálogo

```json
{ "method": "catalogo", "params": {} }
```

### 2. Nominata — PL, dep. federal, 2022, SP

```json
{
  "method": "nominata",
  "params": {
    "ano": 2022,
    "cargo": "deputado_federal",
    "uf": "SP",
    "sg_partido": "PL",
    "limite": 5
  }
}
```

### 3. Votação — presidente, SP, 2º turno 2022, % sobre válidos

```json
{
  "method": "votacao",
  "params": {
    "ano": 2022,
    "cargo": "presidente",
    "uf": "SP",
    "turno": 2,
    "base_pct": "validos",
    "limite": 10
  }
}
```

### 4. Comparecimento — prefeito, Recife (IBGE), 2024

```json
{
  "method": "comparecimento",
  "params": {
    "ano": 2024,
    "cargo": "prefeito",
    "cod_ibge": 2611606,
    "turno": 1
  }
}
```

### 5. Eleitos — governador, PE, 2022

```json
{
  "method": "eleitos",
  "params": {
    "ano": 2022,
    "cargo": "governador",
    "uf": "PE",
    "limite": 20
  }
}
```

### 6. Proposições — PL na Câmara, 2024

```json
{
  "method": "proposicoes",
  "params": {
    "ano": 2024,
    "sigla_tipo": "PL",
    "limite": 5
  }
}
```

### 7. Deputados na Casa — PT em SP

```json
{
  "method": "deputados_casa",
  "params": {
    "uf": "SP",
    "sg_partido": "PT",
    "limite": 5
  }
}
```

### Clima (Radar) — notícia do Flávio na semana

```json
{
  "method": "clima",
  "params": {
    "q": "Flávio",
    "canal": "news",
    "janela_horas": 168,
    "limite": 10
  }
}
```

### Acervo — plano/programa (quando houver carga)

```json
{
  "method": "acervo",
  "params": {
    "query": "segurança pública",
    "ano_eleicao": 2022,
    "tipo": "plano_governo",
    "limite": 5
  }
}
```

## Exemplo REST equivalente

```http
POST /v1/nominata
Content-Type: application/json
Authorization: Bearer <MCP_TOKEN>

{"ano":2022,"cargo":"dep_federal","uf":"SP","sg_partido":"PL","limite":5}
```

## Resposta

Envelope JSON: `status` (`ok` | `fora_recorte` | …), `linhas` (array), metadados. Conjunto vazio = dado **inexistente**, não zero.

## Cursor / agente

Conectar o MCP HTTP deste host com o token acima. Skill do repositório: `.cursor/skills/inteligencia-eleitoral-brasil/SKILL.md`.

## Operação interna (equipe técnica)

Antes de deploy ou módulo novo:

```bash
python scripts/auditar_recorte.py
```

Exit 0 obrigatório. Matriz em `docs/AUDITORIA-RECORTE.md`.

Postgres **não** fica exposto na internet (porta pública fechada). Carga e auditoria local usam tunnel ou job no cluster — ver `docs/ARQUITETURA-RUNTIME.md`.
