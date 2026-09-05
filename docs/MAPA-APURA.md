# Módulo Mapa · Apura (Amapá)

Status: fatia 1+2 (cidades + notas + carreata). Calor por zona = depois.

## Onde

- UI: aba **Mapa** no workspace (após Operar campanha)
- API: `/apura/api/mapa/*`
- Schema: `sql/patch_mapa.sql` (boot via `mapa.schema.ensure_schema`)

## Uso

1. Operar Amapá → **Mapa** (mapa de ruas + contorno dos municípios)
2. **Notas:** clique no município → edite → **Salvar nota**
3. **Carreata:** clique em qualquer ponto/rua do mapa (zoom nas vias) na ordem → prévia OSRM → **Salvar rota**

Malha: `mcp/static/apura/assets/ap-municipios.geojson` (16 municípios).  
Tiles: Esri World Street Map (sem API key). Rota: OSRM (`/mapa/rota-preview`).

## Dados

- 16 municípios AP com centroides em `ctl.municipio_geo`
- Notas: `ctl.mapa_nota` (única por campanha × município)
- Carreatas: `ctl.mapa_caravana` (`pontos_json` + `rota_geojson`)

## Próximo

Mapa de calor por zona eleitoral (precisa geometria de zona TSE).
