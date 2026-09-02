# InteligÃªncia Eleitoral Brasil

Leia `docs/SPEC-BRASIL.md` e `docs/FONTES-NUCLEO.md` antes de ingerir ou responder com cifra.

Recorte: Brasil; presidente a vereador; federais 2014/2018/2022 + 2026 candidatura; municipais 2016/2020/2024.

Fora desse recorte: resposta seca em SPEC-BRASIL.md. Sem estimativa.

**Gate bloqueante:** rode `python scripts/auditar_recorte.py` antes de carga, deploy ou mÃ³dulo novo (contexto, Parlamento, entrega MCP). Exit 1 = parar. Status em `docs/AUDITORIA-RECORTE.md` â€” nÃ£o confiar em `INVENTARIO-INBOX.md` para saber o que jÃ¡ estÃ¡ no banco.

`Arquitetura/` Ã© legado: sÃ³ consultar, nunca gravar. Backlog deste produto nÃ£o Ã© o catÃ¡logo da campanha.

Dump sujo: `inbox/` (somente leitura). CanÃ´nico: `data/` (`data/README.md`).

Entrega MCP: `docs/ENTREGA-MCP.md`.  
Acervo / Radar (trilha B + clima): `docs/ACERVO.md`.
Corte VPS (somente se860g): `docs/CORTE-VPS.md`.

Guia do usuÃ¡rio (pÃ¡gina web): https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/guia  
Landing comercial: https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/  
Apura (acesso interno, nÃ£o pÃºblico): https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/apura/app  
Pedido de demo (pÃºblico): https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/#demo  
Skill portÃ¡til (Claude, GPT, Manus, Cursor): `docs/SKILL-INTELIGENCIA-ELEITORAL.md` ou download na pÃ¡gina /guia.
