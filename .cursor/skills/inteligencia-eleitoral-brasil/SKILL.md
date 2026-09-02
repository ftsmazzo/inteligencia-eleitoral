---
name: inteligencia-eleitoral-brasil
description: >-
  Consulta dados eleitorais oficiais do Brasil via MCP HTTP. Use para votos,
  candidatos, eleitos, contas, populaÃ§Ã£o, CadÃšnico, Bolsa e CÃ¢mara (2014â€“2024 +
  candidatura 2026). Nunca invente cifra. Recuse fora do recorte.
---

# InteligÃªncia Eleitoral Brasil (Cursor)

**Skill completa:** leia e siga `docs/SKILL-INTELIGENCIA-ELEITORAL.md`  
**Guia do usuÃ¡rio:** `docs/GUIA-USUARIO.md`  
**Spec:** `docs/SPEC-BRASIL.md`

## MCP

URL: `https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp`  
Config copiÃ¡vel: `docs/config/mcp-cursor.json` (substituir `SEU_TOKEN_AQUI`)

## Recorte

Brasil Â· presidente a vereador Â· gerais 2014/2018/2022 + 2026 candidatura Â· municipais 2016/2020/2024.

Fora do recorte â†’ texto seco da skill completa. Sem estimativa.

## Regras

- NÃºmero sÃ³ via tools MCP (`catalogo`, `nominata`, `votacao`, `contas_resumo`, â€¦).
- Preferir `contas_resumo` a listar NFs de `despesa` para gastoÃ—voto.
- Lista vazia = inexistente, nÃ£o zero.
- NÃ£o usar campanha NE9 nem `Arquitetura/` como fonte.
- `inbox/` sÃ³ leitura; canÃ´nico em `data/`.
