# Entrega MCP Â· InteligÃªncia Eleitoral Brasil

VersÃ£o 0.1 Â· 26/08/2026

**Guia do usuÃ¡rio (pÃ¡gina web):** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/guia  
**Landing comercial:** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/  
**Pedido de demo:** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/#demo  
**Apura (interno):** https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/apura/app  
**Skill para IAs:** download na pÃ¡gina /guia ou `docs/SKILL-INTELIGENCIA-ELEITORAL.md`

A pessoa designada **nÃ£o recebe login do Postgres**. Acesso sÃ³ via HTTP(S) com token.

## Endpoints

| Uso | URL |
|---|---|
| Health | `https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/health` |
| MCP Fato (JSON) | `POST …/mcp` |
| MCP RAG campanha Amapá | `POST …/mcp/rag` |
| MCP Contexto campanha Amapá | `POST …/mcp/contexto` |
| REST fino | `POST …/v1/<tool>` (mesmo contrato) |

Três servidores, o mesmo token Bearer. RAG e Contexto estão travados em `governador-amapa` (AP, governador, 2026). Cifra **só** no MCP Fato.

Config Cursor/Claude: `docs/config/mcp-cursor.json`.

## AutenticaÃ§Ã£o

Header **um** dos dois:

```http
Authorization: Bearer <MCP_TOKEN>
```

```http
X-Token: <MCP_TOKEN>
```

O valor de `MCP_TOKEN` estÃ¡ no EasyPanel (serviÃ§o **mcp-api** â†’ Environment) e no `.env` local da equipe tÃ©cnica. **Nunca** commitar nem colar o token em chat.

## Recorte (resumo)

Brasil Â· presidente a vereador Â· federais 2014/2018/2022 (+2026 candidatura) Â· municipais 2016/2020/2024.  
Fora do recorte: resposta seca (`docs/SPEC-BRASIL.md`). Sem estimativa.

## Tools disponÃ­veis

`catalogo`, `nominata`, `votacao`, `comparecimento`, `eleitorado`, `coligacao`, `vagas`, `bem`, `receita`, `despesa`, `eleitos`, `populacao`, `cadunico`, `bolsa_familia`, `deputados_casa`, `senadores`, `proposicoes`, `votos_camara`, `depara_parlamentar`, `acervo`, `clima`.

- **acervo** no `/mcp` — Trilha B nacional. Cifra no texto = pista.
- **clima** — Radar sob demanda. Sempre `nivel=indicio`.
- **`/mcp/rag`** — `catalogo`, `acervo`, `acervo_comparar` com UF/ano da campanha Amapá.
- **`/mcp/contexto`** — `escopo`, `memoria`, `temas_plano`, `radar` da mesma campanha. Sem cifra.

## Exemplos MCP (`POST /mcp`)

Corpo: `{ "method": "<tool>", "params": { â€¦ } }`

**Cargos:** use `deputado_federal`, nÃ£o `dep_federal`.

### 1. CatÃ¡logo

```json
{ "method": "catalogo", "params": {} }
```

### 2. Nominata â€” PL, dep. federal, 2022, SP

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

### 3. VotaÃ§Ã£o â€” presidente, SP, 2Âº turno 2022, % sobre vÃ¡lidos

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

### 4. Comparecimento â€” prefeito, Recife (IBGE), 2024

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

### 5. Eleitos â€” governador, PE, 2022

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

### 6. ProposiÃ§Ãµes â€” PL na CÃ¢mara, 2024

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

### 7. Deputados na Casa â€” PT em SP

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

### Clima (Radar) â€” notÃ­cia do FlÃ¡vio na semana

```json
{
  "method": "clima",
  "params": {
    "q": "FlÃ¡vio",
    "canal": "news",
    "janela_horas": 168,
    "limite": 10
  }
}
```

### Acervo â€” plano/programa (quando houver carga)

```json
{
  "method": "acervo",
  "params": {
    "query": "seguranÃ§a pÃºblica",
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

Envelope JSON: `status` (`ok` | `fora_recorte` | â€¦), `linhas` (array), metadados. Conjunto vazio = dado **inexistente**, nÃ£o zero.

## Cursor / agente

Conectar o MCP HTTP deste host com o token acima. Skill do repositÃ³rio: `.cursor/skills/inteligencia-eleitoral-brasil/SKILL.md`.

## OperaÃ§Ã£o interna (equipe tÃ©cnica)

Antes de deploy ou mÃ³dulo novo:

```bash
python scripts/auditar_recorte.py
```

Exit 0 obrigatÃ³rio. Matriz em `docs/AUDITORIA-RECORTE.md`.

Postgres **nÃ£o** fica exposto na internet (porta pÃºblica fechada). Carga e auditoria local usam tunnel ou job no cluster â€” ver `docs/ARQUITETURA-RUNTIME.md`.
