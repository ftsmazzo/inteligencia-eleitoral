# Guia do usuário · Inteligência Eleitoral Brasil

Versão 1.0 · 26/08/2026

Este guia é para **quem usa** a ferramenta — não para quem administra servidor ou banco de dados.

---

## O que é isto?

Uma base **oficial** de dados eleitorais do **Brasil inteiro**: votos, candidatos, eleitos, contas de campanha, população, CadÚnico, Bolsa Família e atividade na Câmara dos Deputados.

Você **pergunta em linguagem normal** (por chat, Cursor, Claude, GPT, Manus etc.) e a IA consulta a base — **sem inventar número**.

**Não é** a ferramenta da campanha NE9. **Não mistura** com notícias ou “achismos”.

---

## O que você pode perguntar

| Tema | Exemplos de pergunta |
|---|---|
| **Votos** | “Quantos votos teve o candidato X em SP no 2º turno de 2022?” |
| **Candidatos** | “Quem foi candidato a deputado federal pelo PL em Pernambuco em 2022?” |
| **Eleitos** | “Quem foi eleito governador do Ceará em 2022?” |
| **Comparecimento** | “Quantos votos válidos, brancos e nulos em Recife na eleição de 2024?” |
| **Coligação** | “Quais partidos compunham a coligação do candidato Y em 2014?” |
| **Contas** | “Quanto o candidato Z declarou de receita em 2022?” |
| **População** | “Qual a população de Fortaleza no censo de 2022?” |
| **Social** | “Quantas famílias no CadÚnico em Recife?” / “Quanto foi repassado de Bolsa Família?” |
| **Câmara** | “Quais PLs foram apresentados em 2024?” / “Quem são os deputados do PT em SP?” |

### Anos disponíveis

| Tipo de eleição | Anos com resultado na urna |
|---|---|
| Presidente, governador, senador, deputados | **2014, 2018, 2022** |
| Prefeito e vereador | **2016, 2020, 2024** |
| Candidaturas 2026 | Só **cadastro** (quem se candidatou) — **sem votos** até a eleição |

### O que **não** dá para perguntar

- Eleições antes de 2014 ou depois do recorte (ex.: 2010, 2028)
- Resultado da eleição de **2026** antes da apuração oficial
- “Estimativas” ou completar lacuna com Nordeste ou outra região
- Pesquisa eleitoral de instituto (não é urna)

Se estiver fora do recorte, a ferramenta responde **secamente** que o dado não existe — não chuta zero.

---

## Passo 1 · Receber seu token

Quem administra o sistema vai te passar um **token secreto** (senha de acesso).  
Guarde em local seguro. **Não** publique, **não** cole em grupo, **não** commite no git.

Você vai colar esse token onde indicado abaixo como `SEU_TOKEN_AQUI`.

---

## Passo 2 · Conectar na sua IA

Escolha **uma** opção conforme a ferramenta que você usa.

### Opção A · Cursor (recomendado)

1. Abra **Cursor Settings → MCP** (ou edite o arquivo de configuração MCP do Cursor).
2. Cole o bloco abaixo e substitua `SEU_TOKEN_AQUI` pelo token recebido:

```json
{
  "mcpServers": {
    "inteligencia-eleitoral-brasil": {
      "url": "https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp",
      "headers": {
        "Authorization": "Bearer SEU_TOKEN_AQUI"
      }
    }
  }
}
```

3. Ative o servidor MCP e reinicie o Cursor se pedido.
4. No chat, peça algo como: *“Use a Inteligência Eleitoral: votos de Lula em SP no 2º turno de 2022.”*

Arquivo pronto para copiar também em: `docs/config/mcp-cursor.json`

---

### Opção B · Claude Desktop / Claude (MCP HTTP)

Se sua versão suporta MCP remoto por URL:

```json
{
  "mcpServers": {
    "inteligencia-eleitoral-brasil": {
      "url": "https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp",
      "headers": {
        "Authorization": "Bearer SEU_TOKEN_AQUI"
      }
    }
  }
}
```

Arquivo: `docs/config/mcp-claude.json`

---

### Opção C · ChatGPT, Manus ou qualquer IA **sem** MCP nativo

1. Copie o conteúdo do arquivo **`docs/SKILL-INTELIGENCIA-ELEITORAL.md`** (ou peça para anexar ao projeto).
2. Cole nas **instruções personalizadas** / **system prompt** / **conhecimento do agente**.
3. Informe à IA:
   - **URL:** `https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp`
   - **Token:** o que você recebeu (só na configuração, não em conversa pública)

A IA deve chamar a API com POST JSON (modelo abaixo).

---

### Opção D · Teste rápido no navegador (Postman / Insomnia / curl)

**URL:**

```
https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/mcp
```

**Cabeçalho:**

```
Authorization: Bearer SEU_TOKEN_AQUI
Content-Type: application/json
```

**Corpo (exemplo — listar o que existe):**

```json
{
  "method": "catalogo",
  "params": {}
}
```

**Corpo (exemplo — candidatos PL em SP, 2022):**

```json
{
  "method": "nominata",
  "params": {
    "ano": 2022,
    "cargo": "deputado_federal",
    "uf": "SP",
    "sg_partido": "PL",
    "limite": 10
  }
}
```

**Corpo (exemplo — votos presidente SP, 2º turno 2022):**

```json
{
  "method": "votacao",
  "params": {
    "ano": 2022,
    "cargo": "presidente",
    "uf": "SP",
    "turno": 2,
    "base_pct": "validos",
    "limite": 20
  }
}
```

---

## Passo 3 · Como formular boas perguntas

Quanto mais claro, melhor a resposta:

1. **Ano** da eleição (ex.: 2022)
2. **Cargo** (presidente, governador, senador, deputado_federal, deputado_estadual, prefeito, vereador)
3. **Onde** — UF (`SP`, `PE`…) ou município (código IBGE de 7 dígitos, se souber)
4. **Quem** — partido, nome de urna ou número, se aplicável

**Bom:** “Votos válidos do Bolsonaro em MG no 2º turno de 2022 para presidente.”  
**Ruim:** “Como foi a eleição?” (falta ano, cargo, lugar)

### Nomes de cargo que funcionam

| Fale assim | Ou assim |
|---|---|
| presidente | pres |
| governador | gov |
| senador | sen |
| deputado federal | deputado_federal |
| deputado estadual | deputado_estadual |
| prefeito | prefeito |
| vereador | vereador |

---

## Passo 4 · Entender a resposta

Toda resposta vem em JSON com:

- **`status`:** `ok` = encontrou dados; `fora_do_recorte` = pedido inválido para esta base
- **`linhas`:** lista de resultados (pode ser vazia)
- Lista vazia = **não existe** na base — **não** significa zero votos

Percentual de votos: peça explícito “sobre votos **válidos**” ou a IA usa `base_pct: "validos"`.

---

## Passo 5 · Skill para a IA (Claude, GPT, Manus, Cursor)

Para a IA **se comportar corretamente**, use o arquivo:

**`docs/SKILL-INTELIGENCIA-ELEITORAL.md`**

- No **Cursor:** já existe skill em `.cursor/skills/inteligencia-eleitoral-brasil/` apontando para ela.
- Em **outras IAs:** copie o conteúdo inteiro para instruções do agente ou anexe ao projeto.

---

## Checklist antes de usar

- [ ] Recebi meu token
- [ ] Conectei MCP ou colei a Skill
- [ ] Testei com `catalogo` ou uma pergunta simples
- [ ] Sei que 2026 ainda não tem urna
- [ ] Sei que número vazio = inexistente, não zero

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| “não autorizado” | Token errado ou ausente no cabeçalho |
| “fora do recorte” | Ano, cargo ou território fora da tabela — reformule |
| Lista vazia | Dado não existe (candidato, município ou combinação) |
| IA inventa número | Reforce: “consulte só a Inteligência Eleitoral Brasil, sem estimar” |

**Teste se o serviço está no ar:** abra no navegador  
https://inteligencia-eleitoral-brasil-mcp-api.kxryyk.easypanel.host/health  
Deve aparecer `{"status":"ok"}`.

---

## Onde saber mais (técnico)

| Documento | Para quem |
|---|---|
| `docs/SKILL-INTELIGENCIA-ELEITORAL.md` | IA / agentes |
| `docs/ENTREGA-MCP.md` | Equipe técnica |
| `docs/catalogo_nucleo.json` | Lista formal de pacotes |
| `docs/SPEC-BRASIL.md` | Recorte oficial |

---

## Resumo em uma frase

**Conecte o MCP com seu token, cole a Skill na IA, pergunte com ano + cargo + lugar — e use só os números que a base devolver.**
