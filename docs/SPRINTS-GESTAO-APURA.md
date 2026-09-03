# Sprints — Gestão Apura

Produto: camada **Gestão** → Chat + Radar com Perfil/dossiê/Base.

## Status

| Sprint | Entrega | Status |
|--------|---------|--------|
| **1** | Schema escopo + wizard + aba Gestão | feito |
| **2** | Motor Base de Verdade + Perfil de Eleitor | feito |
| **3** | Upload HTML → blocos memória | feito |
| **4** | Seed Radar + coordenador + liberar equipe | feito |
| **5** | Apura injeta Perfil + blocos no prompt | feito |

## Fluxo operacional

1. Gestão → Iniciar → ano/cargo/UF/candidato → Salvar escopo  
2. **Gerar Base + Perfil** (motor)  
3. (Opcional) upload dossiê HTML  
4. Seed Radar / Liberar equipe  
5. Equipe usa Chat + Radar; Apura lê `ctl.campanha_memoria`

## API Gestão

| Path | Função |
|------|--------|
| GET/POST status, iniciar, candidatos, escopo, ambiente | S1 |
| POST `/motor` | S2 Base + Perfil (+ seed radar) |
| GET `/memoria` | lista blocos |
| POST `/dossie` | HTML no JSON `{html, nome_arquivo}` |
| POST `/seed-radar` | alvos a partir do escopo |
| POST `/liberar` | pronto + equipe_liberada |

Cifras = Trilha A. Memória = contexto/`indicio` (exceto blocos `nivel=fato` do motor).
