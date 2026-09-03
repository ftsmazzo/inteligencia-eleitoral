# Perfil eleitoral (Gestão) — contrato v2

## Regra 1

Dossiê **não** é fonte deste bloco. Dossiê = memória semântica para o agente.

## O que é

Um único bloco `perfil_eleitor` descrevendo **quem é o eleitor do território** e **quem ganhou o cargo no local** — só Trilha A.

Não busca “perfil do eleitor do candidato”. Não quebra se o candidato nunca concorreu.

## Âncora

| Cargo | Âncora |
|-------|--------|
| Presidente, governador, senador, dep. federal/estadual | 2022 |
| Prefeito, vice, vereador | 2024 |

## Conteúdo (um texto)

1. **Estado** — total + sexo + faixa etária + escolaridade (âncora).  
2. **Partido campeão na UF** — eleito na urna (`api._eh_eleito`).  
3. **Municípios** (maiores eleitorados) — mesmo corte demográfico + **campeão local** (mais votado naquele município no turno final da disputa).  
4. **Apontamentos 2024** (só se a âncora for estadual/federal):  
   - variação de eleitorado e mudanças de composição (≥ 1,5 p.p.)  
   - em cada município: eleitorado âncora→2024 + prefeito eleito 2024  
   - nota fixa: 2024 não substitui a âncora estadual  

Raça/cor: fora até ingestão oficial no `eleicao.eleitorado`.

## Nível e uso no Apura

- `nivel = fato` (cifras e campeões de urna).  
- Apura pode citar à vontade; não misturar com indício de dossiê/Radar.

## Fora de escopo deste bloco

- Voto/proxy do candidato da campanha  
- Dossiê / fichas Acervo como input  
- Segundo perfil paralelo (“eleitor do fulano”)
