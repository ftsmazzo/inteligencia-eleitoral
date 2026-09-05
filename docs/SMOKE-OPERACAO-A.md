# Smoke · Operação A (Amapá / vice)

Objetivo: confirmar que o Trilho A continua operante sem depender do painel de plataforma.

URL: `https://inteligencia-eleitoral-brasil-mcp-api.se860g.easypanel.host/apura/app`  
Hard refresh: `Ctrl+F5`.

## Super gestor (Fred / Leo / Ary)

1. Login → shell com barra **Campanhas em operação**.
2. Clicar **Operar Amapá** (ou Continuar em …) → abre **Chat** com chip da campanha.
3. Enviar uma pergunta com ano/cargo/UF → resposta com cifra oficial (não inventada).
4. Abrir **Radar** (se usam) → carrega sem erro de “sem campanha”.
5. **Painel plataforma** (rodapé) → volta ao shell; atalhos ainda visíveis.
6. **Operar vice / Alfredo** → Chat na outra campanha.

## Colaborador da campanha (1 vínculo)

1. Login → entra direto no workspace (sem shell de plataforma).
2. Chat + 1 pergunta oficial ok.

## Multiagente (após deploy com patch_gestao_v5)

1. Perfil **Estrategista**: no Chat, digite `Ativar Ary` → inicia briefing (não inventa cifra).
2. Pedido de clima/redes com escopo → `consultar_clima` usa candidato do escopo (não frio).
3. Perfil **Operacional**: salvar/listar contato (`telefone do gerente`) e criar tarefa.
4. Smoke estático: `python scripts/smoke_apura_multiagente.py`

## Não é regressão (esperado)

- Super não cai mais automaticamente “dentro” do Amapá no login (precisa Operar).
- Abas Quotas / Conversas / Eventos são painel — não são o fluxo diário.

## Se falhar

- Anotar e-mail, campanha, passo e mensagem de erro.
- Congelar features novas no A; só hotfix de operação.
