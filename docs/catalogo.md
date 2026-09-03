# Catálogo de recursos · Inteligência Eleitoral Brasil

## MCP Fato

- **Tipo:** conector MCP
- **Localização/endpoint:** `POST /mcp` (`https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/mcp`)
- **Fonte dos dados:** Postgres `api.*` (TSE, IBGE, MDS, Câmara) + acervo nacional + clima
- **Frequência de atualização:** sob demanda
- **Como consultar:** `{"method":"votacao","params":{"ano":2022,"cargo":"governador","uf":"AP"}}`
- **Limitações conhecidas:** recorte SPEC-BRASIL; 2026 sem urna
- **Data:** 2026-09-03
- **Responsável técnico:** Cursor

## MCP RAG · campanha Amapá

- **Tipo:** conector MCP
- **Localização/endpoint:** `POST /mcp/rag`
- **Fonte dos dados:** `acervo.documento` / `acervo.chunk` filtrados pela campanha `governador-amapa`
- **Frequência de atualização:** sob demanda (carga de planos)
- **Como consultar:** `{"method":"acervo","params":{"query":"saneamento"}}`
- **Limitações conhecidas:** não é cifra; UF/ano travados; ausência = inexistente
- **Data:** 2026-09-03
- **Responsável técnico:** Cursor

## MCP Contexto · campanha Amapá

- **Tipo:** conector MCP
- **Localização/endpoint:** `POST /mcp/contexto`
- **Fonte dos dados:** `ctl.campanha`, `ctl.campanha_memoria`, `ctl.radar_config`, temas do plano
- **Frequência de atualização:** sob demanda (Gestão / motor)
- **Como consultar:** `{"method":"escopo","params":{}}` · `memoria` · `temas_plano` · `radar`
- **Limitações conhecidas:** memória é `indicio` salvo bloco marcado fato; não substitui `votacao`
- **Data:** 2026-09-03
- **Responsável técnico:** Cursor
