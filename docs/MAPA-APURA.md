# Módulo Mapa · Apura (Amapá)

Status: fatia 1+2 (cidades + notas + carreata). Calor por zona = depois.

## Onde

- UI: aba **Mapa** no workspace (após Operar campanha)
- API: `/apura/api/mapa/*`
- Schema: `sql/patch_mapa.sql` (boot via `mapa.schema.ensure_schema`)

## Uso

1. Operar Amapá → **Mapa**
2. **Notas:** clique no município → edite → **Salvar nota**
3. **Carreata (recomendado):** cole CEPs (1 por linha) → **Gerar rota pelos CEPs** → **Salvar rota**
4. **Carreata (mapa):** alterne camada Ruas/OSM/Satélite → dê zoom → clique nas vias

Malha: `mcp/static/apura/assets/ap-municipios.geojson` (16 municípios).  
Tiles: Carto Voyager + OSM + Esri Imagery (sem API key).  
Geocode: BrasilAPI CEP (+ Nominatim fallback) em `/mapa/geocode-ceps`.  
Rota: OSRM (`/mapa/rota-preview`).

## Dados

- 16 municípios AP com centroides em `ctl.municipio_geo`
- Notas: `ctl.mapa_nota` (única por campanha × município)
- Carreatas: `ctl.mapa_caravana` (`pontos_json` + `rota_geojson`)

## Próximo

Mapa de calor por zona eleitoral (precisa geometria de zona TSE).
