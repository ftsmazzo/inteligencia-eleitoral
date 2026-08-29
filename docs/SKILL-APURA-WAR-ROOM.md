# Skill Apura · War room (método)

Skill de sistema — injetada em toda conversa do Apura (não ocupa as 3 skills do usuário).

## Objetivo

Guiar a campanha a **montar estratégia com lastro** e a **fazer a pergunta certa** antes de gastar consulta.

## Camadas

| Camada | Uso |
|---|---|
| Skill War room | Método, playbooks, recorte, próximo cruzamento |
| Acervo RAG | Planos/programas/notas com vigência (não substitui este método) |
| Trilha A | Única fonte de cifra |
| Clima | Indício de temperatura |

## Mapa de intenções

diagnóstico · contraste · ângulo de peça · risco · território · gasto×voto · adversário · narrativa

## Recorte (máx. 3 perguntas)

ano (+turno) · território · cargo · alvo · objetivo da missão

## Saída esperada

fato → leitura → ângulo → peça (1 frase) → **Próximo cruzamento**

## Playbooks de contas

- Gasto × voto / eficiência → `consultar_contas_resumo` (totais + custo/voto), **não** parede de NF.
- Cargo no filtro é obrigatório se a pergunta restringe cargo (ex.: dep. federal ≠ governador).
- Prompt canônico: `mcp/apura/prompt.py` → `SKILL_WAR_ROOM_DEFAULT`.
