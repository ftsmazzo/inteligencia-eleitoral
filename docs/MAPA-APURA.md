# Módulo Mapa · Apura (Amapá)

Status: fatias 1–3 (notas + carreata + calor). Integração com Chat/Ary = depois.

## Onde

- UI: aba **Mapa** no workspace (após Operar campanha)
- API: `/apura/api/mapa/*`
- Schema: `sql/patch_mapa.sql` (boot via `mapa.schema.ensure_schema`)

## Uso

1. Operar Amapá → **Mapa**
2. **Notas:** clique no município → edite → **Salvar nota**
3. **Carreata:** cole CEPs (1 por linha) → **Gerar rota** → **Salvar rota** → **HTML** (export com endereços + trajeto)
4. **Calor:** ano da urna → municípios coloridos pelo % do candidato da campanha; tabela por zona ao lado

## Limite do calor por zona

Não há GeoJSON oficial de zona no TRE-AP. O mapa pinta **município** (IBGE); a **zona** entra como tabela (Trilha A: `eleicao.votacao`). Macapá tem várias zonas no mesmo polígono municipal.

## Dados

- 16 municípios AP · `ctl.municipio_geo`
- Notas · `ctl.mapa_nota`
- Carreatas · `ctl.mapa_caravana` (+ `GET .../export.html`)
- Calor · `GET /mapa/calor` ← `eleicao.votacao` (candidato da Gestão)

## Parqueado (quando voltar ao Chat)

- Tool para a IA ler notas / carreatas
- HTML da carreata acionado pelo Ary
