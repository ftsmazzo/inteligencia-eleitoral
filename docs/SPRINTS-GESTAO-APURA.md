# Sprints — Gestão Apura

Produto: camada **Gestão** (coordenador configura o ambiente) → Chat + Radar para a equipe, com Perfil/dossiê/Base.

## Modelo

- Gestão = escopo + memória de campanha (não é o chat).
- Dossiê = arquivo enviado (HTML→blocos); não nasce só da Base.
- Perfil de Eleitor = texto indexado (densidade pro Apura).
- Cifras = Trilha A / tools; memória contextualiza.
- Tabelas em `ctl.*` ligadas a `ctl.campanha`.

## Mapa

| Sprint | Entrega | Status |
|--------|---------|--------|
| **1 — Fundação** | Schema escopo + wizard ano/cargo/UF/candidato + aba Gestão + status | em curso |
| **2 — Motor** | Snapshot oficial → blocos + Perfil de Eleitor indexado | pendente |
| **3 — Dossiê** | Upload HTML → blocos tipados | pendente |
| **4 — Radar + liberação** | Seed alvos/IG; papel coordenador; liberar equipe | pendente |
| **5 — Apura estratégico** | Prompt injeta Perfil + blocos + clima | pendente |

## Sprint 1 — DoD

- [x] `sql/patch_gestao.sql` + `ctl.campanha_memoria`
- [x] API `/apura/api/gestao/{status,iniciar,candidatos,escopo,ambiente}`
- [x] Aba Gestão no Apura com wizard
- [x] Banner se `rascunho|configurando`; `legado` sem banner
- [ ] Deploy se860g smoke

Campanhas existentes: `ambiente_status=legado` (Chat/Radar iguais).

## API (S1)

| Método | Path | Função |
|--------|------|--------|
| GET | `/apura/api/gestao/status` | Escopo + flags |
| POST | `/apura/api/gestao/iniciar` | `legado`→`rascunho` (ou nova campanha) |
| GET | `/apura/api/gestao/candidatos` | Nominata 2026 |
| POST | `/apura/api/gestao/escopo` | Grava candidato; →`configurando` |
| POST | `/apura/api/gestao/ambiente` | `rascunho\|configurando\|pronto` |
