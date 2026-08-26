# Arquitetura de runtime · Inteligência Eleitoral Brasil

A pessoa designada conecta **só o MCP**. Não recebe usuário do Postgres.

## EasyPanel · `inteligencia-eleitoral-brasil`

Dois serviços no dia 1:

1. **postgres** (16+) — volume persistente, backup. Extensões: `pg_trgm`; `vector` só quando houver trilha B. **Sem porta publicada na internet** — só rede interna (`postgres:5432` para o `mcp-api`). Administração/carga: tunnel SSH ou job no EasyPanel.
2. **mcp-api** — app Python atrás de HTTPS. Rotas: `/health`, `/mcp`. Token no header. A mesma app pode expor REST fino (`/v1/votacao`) que chama as **mesmas** funções SQL — um contrato, dois transportes.

Não neste projeto: Redis, OpenSearch, o Postgres de clipping, o MCP da campanha, o serviço `pesquisas`.

Ingestão: job separado (mesmo cluster, sem porta pública) quando o DDL existir. Não misturar ingestão com o processo do MCP.

## Um banco, não dois

Cifra de urna cabe em um Postgres se a consulta **sempre** recortar ano e território. Segundo banco (OLAP, warehouse) não ganha desempenho aqui; só duplica operação.

Clipping/redes continuam **irmãos**: outro banco ou outro schema, `nivel=indicio`, outra credencial MCP.

## Modelagem (não reusar `fato.serie_municipal` como urna)

Grão do voto: `eleicao × cargo × turno × município × zona × candidato`.

Schemas:

- `ref` — municipio (IBGE 7 + TSE), eleicao, cargo, partido  
- `eleicao` — candidatura, votacao (**partição por ano**), detalhe_munzona, eleitorado, coligacao  
- `api` — funções nomeadas; role `agente` só `EXECUTE`  
- `ctl` — execução, QA, âncora  

Percentual `validos` vs `soma_dois` só na função. UF/Brasil = soma, nunca rateio.

## MCP (poucas tools)

`catalogo`, `votacao`, `comparecimento`, `nominata`, `eleitorado`, `coligacao`, `vagas`, `bem`, `receita`, `despesa`, `eleitos`, `populacao`, `cadunico`, `bolsa_familia`.  
`votacao`/`eleitos` exigem `ano` + `cargo` + (`uf` ou `cod_ibge`), salvo totais nacionais explícitos. Sem SQL livre. Fora do recorte: texto seco da spec.

## Desempenho

Ordem de grandeza: dezenas a ~10⁸ linhas de votação mun/zona. Postgres 16 + partição por ano + índices `(ano, uf, cargo)` e `(cod_ibge, ano, cargo)`. Pool pequeno no MCP (consultas curtas). Sem “ranking Brasil sem filtro” como tool padrão.
