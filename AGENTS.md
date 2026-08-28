# Inteligência Eleitoral Brasil

Leia `docs/SPEC-BRASIL.md` e `docs/FONTES-NUCLEO.md` antes de ingerir ou responder com cifra.

Recorte: Brasil; presidente a vereador; federais 2014/2018/2022 + 2026 candidatura; municipais 2016/2020/2024.

Fora desse recorte: resposta seca em SPEC-BRASIL.md. Sem estimativa.

**Gate bloqueante:** rode `python scripts/auditar_recorte.py` antes de carga, deploy ou módulo novo (contexto, Parlamento, entrega MCP). Exit 1 = parar. Status em `docs/AUDITORIA-RECORTE.md` — não confiar em `INVENTARIO-INBOX.md` para saber o que já está no banco.

`Arquitetura/` é legado: só consultar, nunca gravar. Backlog deste produto não é o catálogo da campanha.

Dump sujo: `inbox/` (somente leitura). Canônico: `data/` (`data/README.md`).

Entrega MCP: `docs/ENTREGA-MCP.md`.  
Acervo / Radar (trilha B + clima): `docs/ACERVO.md`.

Guia do usuário (página web): https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/guia  
Landing comercial: https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/  
Apura (chat): https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/apura  
Skill portátil (Claude, GPT, Manus, Cursor): `docs/SKILL-INTELIGENCIA-ELEITORAL.md` ou download na página /guia.
