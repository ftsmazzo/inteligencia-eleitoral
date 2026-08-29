---
name: inteligencia-eleitoral-brasil
description: >-
  Consulta dados eleitorais oficiais do Brasil via MCP HTTP. Use para votos,
  candidatos, eleitos, contas, população, CadÚnico, Bolsa e Câmara (2014–2024 +
  candidatura 2026). Nunca invente cifra. Recuse fora do recorte.
---

# Inteligência Eleitoral Brasil (Cursor)

**Skill completa:** leia e siga `docs/SKILL-INTELIGENCIA-ELEITORAL.md`  
**Guia do usuário:** `docs/GUIA-USUARIO.md`  
**Spec:** `docs/SPEC-BRASIL.md`

## MCP

URL: `https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp`  
Config copiável: `docs/config/mcp-cursor.json` (substituir `SEU_TOKEN_AQUI`)

## Recorte

Brasil · presidente a vereador · gerais 2014/2018/2022 + 2026 candidatura · municipais 2016/2020/2024.

Fora do recorte → texto seco da skill completa. Sem estimativa.

## Regras

- Número só via tools MCP (`catalogo`, `nominata`, `votacao`, `contas_resumo`, …).
- Preferir `contas_resumo` a listar NFs de `despesa` para gasto×voto.
- Lista vazia = inexistente, não zero.
- Não usar campanha NE9 nem `Arquitetura/` como fonte.
- `inbox/` só leitura; canônico em `data/`.
