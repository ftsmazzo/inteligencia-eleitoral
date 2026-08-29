# Acervo · Trilha B (semântica) + Radar (clima dinâmico)

Versão 0.1 · 27/08/2026  
Produto: Inteligência Eleitoral Brasil (não é a campanha NE9).

## Objetivo

Dar ao Apura/MCP **matéria-prima textual com temporalidade** para cruzar com a Trilha A (urna, eleitos, votos). Sem acervo, o redator “enche linguiça”; com acervo + clima, monta **narrativa ancorada**.

| Camada | O que é | Número? |
|---|---|---|
| **A · Fato** | Postgres `api.*` (TSE, IBGE, Câmara…) | Sim — única fonte de cifra |
| **B · Acervo** | Textos oficiais/técnicos indexados (pgvector) | Não — cifra no texto é *pista* |
| **C · Radar** | Clima de redes/notícias em tempo quase real | Não — sempre `nivel=indicio` |

Radar de referência (painel de campanha): [Radar Eleitoral](https://inteligencia-eleitora-painel.kxryyk.easypanel.host/).

---

## Regras (bloqueantes)

1. **Cifra só na Trilha A.** Trecho do acervo ou item do Radar que cite “3 senadores” **não** vira fato.
2. **Temporalidade obrigatória.** Consulta semântica filtra `vigencia` / `ano_eleicao` / janela do Radar **antes** do ranking vetorial.
3. **Nível explícito na resposta:** `referencia` (oficial) vs `indicio` (clima/notícia).
4. **Campanha isolada.** Radar usa `campaign_id`; o MCP Brasil não mistura stream de uma chapa como “verdade nacional”.
5. **Fora do recorte** (SPEC): resposta seca; acervo/Radar não “completaram” ano ou cargo inexistente.

---

## O que entra no Acervo (estático / curado)

Cada documento: `tipo`, `vigencia_inicio`, `vigencia_fim`, `ano_eleicao`, `escopo` (BR|UF|mun), `nivel`, `fonte_url`, `sha256`.

### MVP (ordem de carga)

1. **Planos de governo — presidente** (2014, 2018, 2022; 2026 quando publicado)  
2. **Programas / estatutos partidários** por ciclo (usar linha PL↔PSL, MDB↔PMDB via `ref.partido_linha`)  
3. **Resoluções e notas TSE** do ciclo (coligação 2014 ≠ federação 2022, calendário, cláusulas)  
4. **Fichas territoriais curtas** geradas da Trilha A (ex.: perfil eleitoral UF) — texto derivado, não PDF externo  
5. **Glossário de campanha** (`tipo=glossario`) — FEFC, quociente, turno, sq_candidato, trilhas A/B/C  
6. **Playbooks de estratégia** (`tipo=playbook_estrategia`) — gasto×voto, cadeiras, território, ângulo, risco, pergunta certa

Seeds versionados em `mcp/seed/acervo_*.jsonl` (bootstrap no startup do `mcp-api`).

### Depois

- Planos de governador (UF sob demanda)  
- **Promoção de planos presidente 2018/2022** a partir de PDF oficial em `data/raw/` (ainda não no seed — não inventar texto de plano)  
- Resumos semânticos de proposições/votos Câmara por tema + ano  
- Trechos de legislação eleitoral vigente por ano (não PDF monolítico)

### Não entra no MVP

- Clipping como fato  
- Pesquisa eleitoral sem módulo próprio  
- PDF temático NE9 (ANP, CNES…)  
- Stream bruto do Radar gravado como documento “oficial”  
- Manual genérico de marketing político sem vigência/escopo

---

## Radar · clima dinâmico (camada C)

O Radar já faz coleta multi-canal (Instagram, X, Facebook, YouTube, TikTok, notícia), classifica (ataque/defesa/oportunidade…), urgência e alvos — isolado por `campaign_id` ([painel](https://inteligencia-eleitora-painel.kxryyk.easypanel.host/)).

### Como usar no produto Brasil

**Consulta livre, sem trava de campanha.** O MCP `clima` usa os **mesmos motores** do Radar (Google News RSS + Apify Instagram) sob demanda:

| Pedido do usuário | Params típicos | Motor |
|---|---|---|
| “notícia do Flávio esta semana” | `q=Flávio`, `canal=news`, `janela_horas=168` | Google News RSS |
| “Instagram do Lula” / `@lulaoficial` | `q=Lula` ou `lulaoficial`, `canal=instagram` | Apify (qualquer @handle) |
| “ataques em segurança nas últimas 24h” | `q=segurança`, `tipo=ataque`, `janela_horas=24` | RSS (+ painel se houver) |

`campaign_id` é **opcional** e só isola o stream HTML do [painel](https://inteligencia-eleitora-painel.kxryyk.easypanel.host/). O default **não** depende de perfil cadastrado.

Env no `mcp-api`: `APIFY_TOKEN`, `APIFY_IG_ACTOR` (default `apify/instagram-scraper`).

Não copiar o banco do Radar para `data/`.
### Papel na narrativa

| Pergunta do usuário | A | B | C (Radar) |
|---|---|---|---|
| Quantas cadeiras o PL ganhou no NE? | eleitos | — | — |
| O que o plano de 2022 dizia sobre segurança? | — | plano_governo | — |
| Como amarrar o crescimento do PL no NE à narrativa de agora? | eleitos | plano/partido | clima 24–72h nos eixos relevantes |
| O adversário está atacando no tema X? | opcional | opcional | clima filtrado por alvo/tipo |

**Narrativa fortalecida** = fato (A) + compromisso/programa (B) + temperatura do debate (C), com rótulos claros:

> **Fato (TSE):** …  
> **Programa (acervo, 2022):** …  
> **Clima (Radar, 24h, indício):** …

### O que o Radar *não* substitui

- Resultado de urna  
- Contagem de cadeiras  
- População / CadÚnico  
- Qualquer % inventado a partir de “clima 68”

---

## Contrato MCP (tools)

| Tool | Camada | Params essenciais |
|---|---|---|
| `consultar_acervo` | B | `query`, `ano_eleicao?`, `tipo?`, `uf?`, `vigente_em?`, `limite` |
| `consultar_clima` | C | `q?`, `canal?`, `origem?`, `tipo?`, `janela_horas?`, `campaign_id?` (opcional) |

Resposta sempre com:

```json
{
  "status": "ok",
  "nivel": "referencia|indicio",
  "nota_metodologica": "...",
  "itens": [
    {
      "titulo": "...",
      "trecho": "...",
      "score": 0.81,
      "vigencia": {"inicio": "2022-01-01", "fim": null},
      "fonte_url": "...",
      "tipo": "plano_governo",
      "canal": null
    }
  ]
}
```

---

## Apura · orquestração

1. Orquestrador chama **A** para cifras.  
2. Se a pergunta for programa / por quê / narrativa / “o que dizer”, chama **B**.  
3. Se pedir clima, redes, “o que está bombando”, ou skill de marketing pedir narrativa viva, chama **C**.  
4. Redator **proibido** de inventar cruzamento: só usa o que veio nas três bandejas.  
5. Estrutura padrão da resposta analítica: fato → programa/contexto → clima (se houver) → implicação de campanha.

Isso reduz linguiça: sem item B/C, o redator admite lacuna em vez de improvisar.

---

## Schema (resumo)

Ver `sql/patch_acervo.sql`:

- `acervo.documento` — metadados + temporalidade  
- `acervo.chunk` — texto + `embedding vector`  
- Índices por `tipo`, `ano_eleicao`, vigência, GIN em tags  

Extensão: `vector` (pgvector). Embeddings: modelo fixo documentado em `meta.modelo_embedding` (troca exige reindex).

Radar: **sem tabela espelho** no MVP; proxy HTTP autenticado para a API do painel (URL/credencial só em env EasyPanel).

---

## Pastas de dado

```
data/raw/acervo_plano_governo/<YYYY-MM-DD>/
data/raw/acervo_programa_partido/<YYYY-MM-DD>/
data/raw/acervo_nota_tse/<YYYY-MM-DD>/
```

`inbox/` continua só leitura. PDF/HTML promovidos com SHA-256 + `meta.json` (FONTES / data/README).

---

## Roadmap

| Fase | Entrega |
|---|---|
| 0 | Este doc + DDL `patch_acervo.sql` |
| 1 | Extensão pgvector no Postgres + tool `consultar_acervo` (stub → busca lexical se embedding ausente) |
| 2 | Carga planos presidente 2018 e 2022 (**pendente** — promover PDF oficial para `data/raw/`) |
| 2b | **Carga planos presidente 2026** (seed `mcp/seed/acervo_planos_2026.jsonl` + bootstrap no startup) |
| 2c | **Glossário + playbooks + notas TSE extras** (`acervo_glossario_*.jsonl`, `acervo_playbook_*.jsonl`) |
| 2d | **Fichas territoriais 2018 e 2022** (bootstrap Trilha A, 27 UFs) |
| 3 | Conector `consultar_clima` → API Radar (env `RADAR_API_URL` + token) |
| 4 | Apura: orquestrador chama B/C; redator com template fato/programa/clima |
| 5 | Programas partidários + notas TSE |

---

## Env (fase 3+)

```
RADAR_API_URL=https://…
RADAR_API_TOKEN=…
RADAR_DEFAULT_CAMPAIGN_ID=…   # opcional
ACERVO_EMBEDDING_MODEL=…      # documentar versão
```

Nunca commitar token. Campanha do Radar ≠ usuário Apura: mapear com cuidado (um cliente Apura pode ter zero ou N `campaign_id`).
