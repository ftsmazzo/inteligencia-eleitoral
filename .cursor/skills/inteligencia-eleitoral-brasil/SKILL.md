---
name: inteligencia-eleitoral-brasil
description: >-
  Recorte e recusa da Inteligência Eleitoral Brasil (não a campanha NE9).
  Use ao consultar urna, candidato, município, TSE, cargo, presidente a
  vereador, MCP desta base, ou ao recusar pergunta fora de 2014–2026 federal /
  2016–2024 municipal.
---

# Inteligência Eleitoral Brasil

Spec: `docs/SPEC-BRASIL.md`. Fontes: `docs/FONTES-NUCLEO.md`.

## Recorte

- Brasil (não default Nordeste).
- Cargos: presidente, governador, senador, deputado federal, deputado estadual, prefeito, vereador.
- Federais/estaduais: 2014, 2018, 2022 (resultado). 2026 = candidatura viva; resultado só após urna oficial.
- Municipais: 2016, 2020, 2024.
- Quebra 2014 vs 2018+: coligação proporcional. Percentual: válidos ≠ soma de dois.

## Fora do recorte

Não estimar. Não usar MCP/skill da campanha Ary. Texto seco:

> Fora do recorte. O escopo da solicitação não faz parte do recorte desta ferramenta, que é: Brasil; cargos de presidente a vereador; eleições federais/estaduais 2014, 2018 e 2022 (resultado) e 2026 (candidatura, resultado após a urna); eleições municipais 2016, 2020 e 2024. Pedido: [resumir o que pediram]. Dado inexistente neste recorte.

## Pastas

Não gravar em `Arquitetura/`. `inbox/` só leitura. Promoção de dump → `data/raw/`.

## MCP (quando existir)

Função nomeada só. Sem SQL livre. Catálogo deste produto, não as 247 tools NE9.
Pacotes: catalogo, nominata, votacao, comparecimento, eleitorado, coligacao, vagas, bem, receita, despesa, eleitos, populacao, cadunico, bolsa_familia.
Trilha B / scrap = `indicio`, nunca cifra oficial.
