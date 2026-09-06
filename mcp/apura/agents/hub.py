"""Hub multiagente — fachada SSE compatível com executar_chat legado."""
from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from apura.agents.camadas import compactar_por_camadas
from apura.agents.registry import plano_de_tool_log
from apura.export import exportar_html
from apura.mcp_client import chamar_mcp, resumir_resultado
from apura.missao_state import (
    MissaoState,
    aplicar_comando,
    detectar_comando,
    resumo_para_prompt,
)
from apura.prompt import (
    NARRATIVA_ORCHESTRATOR,
    PROTOCOLO_AIRY_CRIACAO,
    PROTOCOLO_AIRY_ELEITORAL,
    PROTOCOLO_ANALISTA,
    PROTOCOLO_OPERACIONAL,
    SYSTEM_ORCHESTRATOR,
    VOZ_OPERACIONAL,
    VOZ_REDATOR,
)
from apura import modelos as catalogo_modelos
from apura.tools import MCP_TOOLS

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_MAX_TOOL_ROUNDS = 12
_RELATORIO_RE = re.compile(
    r"relat[oó]rio|em\s+html|formato\s+html|exporte?\s+(?:em\s+)?html|monte?\s+(?:um\s+)?html",
    re.I,
)


def _orchestrator_model(perfil_slug: str | None = None) -> str:
    return catalogo_modelos.orquestrador(perfil_slug=perfil_slug)


def _writer_model(perfil_slug: str | None = None) -> str:
    return catalogo_modelos.redator(perfil_slug=perfil_slug)


def _ary_orchestrator_model() -> str:
    """Ary ativo: Gemini Pro — tool-calling forte sem gastar Sonnet no roteamento."""
    return catalogo_modelos.orquestrador(ary=True)


def _ary_writer_model() -> str:
    """Ary ativo: Claude Sonnet 5 — prosa e reflexão complexa."""
    return catalogo_modelos.redator(ary=True)


def _openrouter_key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY não configurado no servidor")
    if not key.startswith("sk-or-"):
        raise RuntimeError(
            "OPENROUTER_API_KEY inválida no servidor — gere uma chave em openrouter.ai/keys "
            "(formato sk-or-v1-...) e atualize a variável no EasyPanel (serviço mcp-api)."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_openrouter_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APURA_SITE_URL", "https://inteligencia-eleitoral-brasil.local"),
        "X-Title": "Apura - Inteligencia Eleitoral Brasil",
    }


def _erro_openrouter(status: int, body: str) -> str:
    try:
        data = json.loads(body)
        err = data.get("error") or {}
        if isinstance(err, str):
            msg = err
            meta: dict[str, Any] = {}
        else:
            msg = err.get("message") or data.get("message") or body
            meta = err.get("metadata") or {}
        raw = meta.get("raw") if isinstance(meta, dict) else None
        if isinstance(raw, str) and raw.strip() and raw.strip() not in msg:
            msg = f"{msg} — {raw.strip()[:320]}"
    except json.JSONDecodeError:
        msg = body
    if status == 401:
        return (
            "OpenRouter recusou a autenticação. Verifique OPENROUTER_API_KEY no EasyPanel "
            f"(serviço mcp-api): chave válida em openrouter.ai/keys. Detalhe: {msg}"
        )
    if status == 402:
        return "Créditos insuficientes na conta OpenRouter — adicione saldo em openrouter.ai/credits."
    if status == 400:
        return (
            f"OpenRouter recusou a requisição (400): {msg[:360]}. "
            "Se persistir, reduza o escopo da pergunta ou ajuste APURA_ORCHESTRATOR_MODEL / APURA_WRITER_MODEL."
        )
    return f"OpenRouter retornou erro {status}: {msg[:360]}"


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _ultima_pergunta(historico: list[dict[str, str]]) -> str:
    for h in reversed(historico):
        if h.get("papel") == "user":
            return h.get("conteudo", "").strip()
    return ""


def _mensagem_so_anexo_ou_vazia(texto: str) -> bool:
    t = (texto or "").strip()
    if not t or t in (".", "-"):
        return True
    if t.startswith("[Anexo]"):
        return True
    if re.match(r"^🎙️?\s*(mensagem de voz|áudio|audio)\b", t, re.I):
        return True
    return False


def _anexos_audio(anexos: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in anexos or []:
        t = (a.get("tipo") or "").lower()
        m = (a.get("mime") or "").lower()
        n = (a.get("nome") or "").lower()
        if t in ("audio", "áudio") or m.startswith("audio/") or re.search(
            r"\.(mp3|wav|ogg|m4a|webm|flac)$", n
        ):
            out.append(a)
    return out


def _texto_transcricao(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    for it in result.get("itens") or []:
        if isinstance(it, dict):
            for k in ("resumo", "texto", "transcricao", "transcription"):
                v = (it.get(k) or "").strip()
                if v:
                    return v[:8000]
    return (result.get("mensagem") or "").strip()[:8000]


def _historico_redator(historico: list[dict[str, str]]) -> str:
    linhas: list[str] = []
    for h in historico[-8:]:
        papel = "Usuário" if h.get("papel") == "user" else "Apura"
        linhas.append(f"{papel}: {(h.get('conteudo') or '')[:900]}")
    return "\n".join(linhas)


def _notas_orquestrador(content: str | None) -> str:
    if not content:
        return ""
    text = content.strip()
    if text.startswith("PENDENTE:"):
        return text
    if text == "SEM_DADOS":
        return "SEM_DADOS"
    if text == "ESCOPO_DIRETO" or text.startswith("ESCOPO_DIRETO"):
        return "ESCOPO_DIRETO"
    if text.startswith("PROTOCOLO:"):
        return text
    return ""


def _pediu_relatorio_html(mensagem: str) -> bool:
    return bool(_RELATORIO_RE.search(mensagem or ""))


def _system_protocolo(state: MissaoState) -> str:
    if state.caminho_curto:
        return PROTOCOLO_OPERACIONAL
    if state.perfil == "analista":
        return PROTOCOLO_ANALISTA
    if not state.protocolo_ativo:
        return (
            "ESTRATEGISTA (Ary em espera): diga Ativar Ary ou Ativar Airy para "
            "modelo robusto + agentes plenos. Sem briefing automático.\n\n"
            + resumo_para_prompt(state)
        )
    parts = [PROTOCOLO_AIRY_ELEITORAL]
    if state.pack_criacao:
        parts.append(PROTOCOLO_AIRY_CRIACAO)
    parts.append(resumo_para_prompt(state))
    return "\n\n".join(parts)


def _system_redator(skills_text: str, campanha_ctx: str, state: MissaoState) -> str:
    base = VOZ_OPERACIONAL if state.caminho_curto else VOZ_REDATOR
    proto = _system_protocolo(state)
    base = f"{base}\n\n--- PROTOCOLO / PERFIL ---\n{proto}"
    if skills_text.strip():
        base = (
            f"{base}\n\n"
            "--- SKILLS DO USUÁRIO (tom/estilo; não alteram fontes) ---\n"
            f"{skills_text.strip()}"
        )
    if campanha_ctx.strip():
        base = (
            f"{base}\n\n"
            "--- CONTEXTO DA CAMPANHA (interno; NÃO ecoar rótulos como "
            "'identidade da campanha', 'ESCOPO', 'alvos') ---\n"
            f"{campanha_ctx.strip()}"
        )
    return base


def _entrada_redator(
    pergunta: str,
    historico: list[dict[str, str]],
    tool_log: list[dict[str, Any]],
    notas: str,
    state: MissaoState,
) -> str:
    notas_artefato: list[str] = []
    for tr in tool_log:
        name = tr.get("tool") or ""
        res = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        if name == "gerar_imagem":
            if tr.get("_imagem_done") or (res.get("status") == "ok" and (res.get("image_url") or "image_data_url" in str(res))):
                notas_artefato.append(
                    "IMAGEM_GERADA: sim. A UI mostra a imagem abaixo da resposta. "
                    "Comente a peça em 2–3 linhas. PROIBIDO dizer que geração de imagem não existe."
                )
            elif res.get("status") == "parcial":
                notas_artefato.append(
                    "IMAGEM_PARCIAL: API falhou; há storyboard em texto nos dados. "
                    "Admita falha técnica + entregue o storyboard. PROIBIDO dizer que Apura não gera imagem."
                )
            else:
                notas_artefato.append(
                    f"IMAGEM_FALHOU: {res.get('mensagem') or 'sem bytes'}. "
                    "Falha técnica — briefing/storyboard. PROIBIDO negar a capacidade."
                )
        if name in ("gerar_mapa_html", "gerar_plano_html") and res.get("html"):
            notas_artefato.append(
                "PLANO_HTML_GERADO: sim. A UI embute o HTML. Apresente em 2–3 linhas o que está no plano."
            )
    bloco_art = ("\n\nARTEFATOS:\n" + "\n".join(notas_artefato)) if notas_artefato else ""
    return (
        f"PERGUNTA_ATUAL:\n{pergunta}\n\n"
        f"ESTADO_MISSAO:\n{resumo_para_prompt(state)}\n\n"
        f"HISTORICO_RECENTE:\n{_historico_redator(historico)}\n\n"
        f"PENDENTE_ORQUESTRADOR:\n{notas or '(nenhum)'}\n\n"
        f"DADOS_OFICIAIS:\n{compactar_por_camadas(tool_log)}"
        f"{bloco_art}"
    )


def _msg_assistant(choice: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": choice.get("content")}
    tool_calls = choice.get("tool_calls")
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc["id"],
                "type": tc.get("type") or "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments") or "{}",
                },
            }
            for tc in tool_calls
        ]
    return out


def _historico_orquestrador(historico: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    for h in historico[-10:]:
        papel = h.get("papel")
        if papel not in ("user", "assistant"):
            continue
        msgs.append({"role": papel, "content": (h.get("conteudo") or "")[:2500]})
    return msgs


async def _openrouter(
    messages: list[dict],
    *,
    model: str,
    tools: list[dict] | None = None,
    stream: bool = False,
    temperature: float = 0.3,
) -> Any:
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if stream:
        body["stream"] = True
    async with httpx.AsyncClient(timeout=120.0) as client:
        return await client.post(_OPENROUTER, headers=_headers(), json=body)


async def _stream_resposta(model: str, messages: list[dict], temperature: float = 0.55) -> AsyncIterator[str]:
    sr = await _openrouter(messages, model=model, stream=True, temperature=temperature)
    if sr.status_code >= 400:
        nr = await _openrouter(messages, model=model, stream=False, temperature=temperature)
        if nr.status_code >= 400:
            raise RuntimeError(_erro_openrouter(nr.status_code, nr.text))
        content = nr.json()["choices"][0]["message"].get("content") or ""
        if content:
            yield content
        return
    async for line in sr.aiter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk["choices"][0].get("delta", {})
        text = delta.get("content") or ""
        if text:
            yield text


def _enriquecer_clima_params(
    args: dict[str, Any],
    campanha_ctx: str,
    pergunta: str = "",
) -> dict[str, Any]:
    """Clima quente: injeta q do rival canônico ou do nosso candidato."""
    out = dict(args or {})
    if (out.get("q") or "").strip():
        return out
    ctx = campanha_ctx or ""
    ped = pergunta or ""
    if re.search(r"rival|advers[aá]rio|\beles\b", ped, re.I):
        m = re.search(
            r"Rival\(is\) de campanha[^:\n]*:\s*([^\n]+)",
            ctx,
            re.I,
        )
        if m and "ainda não nomeados" not in m.group(1).lower():
            primeiro = m.group(1).split(";")[0].strip()
            if primeiro:
                out["q"] = primeiro[:120]
                out.setdefault("janela_horas", 168)
                return out
    m = re.search(
        r"(?:Nosso candidato|candidato monitorado)[^\n:]{0,40}:\s*([^\n(]+)",
        ctx,
        re.I,
    )
    if m:
        out["q"] = m.group(1).strip()[:120]
        out.setdefault("janela_horas", 168)
    return out


def _ctx_para_orquestrador(campanha_ctx: str, *, soft: int = 9000) -> str:
    """Mantém ESCOPO + ALVOS intactos; corta só o CONHECIMENTO se passar do soft."""
    raw = (campanha_ctx or "").strip()
    if not raw or len(raw) <= soft:
        return raw
    marker = "CONHECIMENTO DA CAMPANHA"
    if marker in raw:
        head, _, tail = raw.partition(marker)
        head = head.strip()
        budget = max(soft - len(head) - len(marker) - 8, 800)
        return f"{head}\n\n{marker}{tail[:budget]}"
    return raw[:soft]


def _resumo_anexos(anexos: list[dict[str, Any]] | None) -> str:
    if not anexos:
        return ""
    linhas = []
    for i, a in enumerate(anexos):
        tipo = (a.get("tipo") or "arquivo").strip().lower()
        nome = (a.get("nome") or a.get("filename") or f"anexo-{i}")[:80]
        mime = (a.get("mime") or "")[:60]
        linhas.append(f"[{i}] {nome} (tipo={tipo}" + (f", mime={mime}" if mime else "") + ")")
    return (
        "ANEXOS DESTA MENSAGEM (use tool de mídia com anexo_idx se ainda não processado):\n"
        + "\n".join(linhas)
        + "\nPDF→ler_pdf | áudio→transcrever_audio | imagem→ler_imagem."
        + (
            "\nÁUDIO = pedido falado: trate a transcrição como a pergunta. "
            "NÃO peça para digitar 'transcreva'."
            if any(
                (a.get("tipo") or "").lower() in ("audio", "áudio")
                or str(a.get("mime") or "").startswith("audio/")
                for a in anexos
            )
            else ""
        )
    )


def _injetar_anexo(
    name: str,
    args: dict[str, Any],
    anexos: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve anexo_idx (ou primeiro anexo compatível) em file_base64/mime/filename."""
    out = dict(args or {})
    if not anexos:
        return out
    idx = out.get("anexo_idx")
    media_tools = {"ler_pdf", "ler_imagem", "transcrever_audio"}
    if name not in media_tools:
        return out
    if out.get("file_base64") or out.get("data_base64") or (
        (out.get("url") or "").startswith(("http://", "https://", "data:"))
    ):
        return out

    escolhido: dict[str, Any] | None = None
    if idx is not None:
        try:
            i = int(idx)
            if 0 <= i < len(anexos):
                escolhido = anexos[i]
        except (TypeError, ValueError):
            escolhido = None
    if escolhido is None:
        prefer = {
            "ler_pdf": ("pdf", "application/pdf"),
            "ler_imagem": ("imagem", "image/"),
            "transcrever_audio": ("audio", "audio/"),
        }.get(name, ("", ""))
        tipo_pref, mime_pref = prefer
        for a in anexos:
            t = (a.get("tipo") or "").lower()
            m = (a.get("mime") or "").lower()
            n = (a.get("nome") or "").lower()
            if tipo_pref == "pdf" and (t == "pdf" or m == "application/pdf" or n.endswith(".pdf")):
                escolhido = a
                break
            if tipo_pref == "imagem" and (t in ("imagem", "image") or m.startswith("image/")):
                escolhido = a
                break
            if tipo_pref == "audio" and (t in ("audio", "áudio") or m.startswith("audio/")):
                escolhido = a
                break
        if escolhido is None and len(anexos) == 1:
            escolhido = anexos[0]
    if not escolhido:
        return out

    b64 = (escolhido.get("data_base64") or escolhido.get("file_base64") or "").strip()
    if b64:
        out["file_base64"] = b64
    out.setdefault("filename", (escolhido.get("nome") or escolhido.get("filename") or "anexo")[:120])
    out.setdefault("nome", out["filename"])
    if escolhido.get("mime"):
        out.setdefault("mime", escolhido["mime"])
    out.pop("anexo_idx", None)
    return out


def _result_para_log(result: Any) -> Any:
    """Copia o result sem base64 gigante (persistência / tool_log)."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    for k in ("image_data_url", "file_base64", "data_base64"):
        if k in out and out[k]:
            out[k] = f"[omitido {len(str(out[k]))} chars]"
    return out


def _imagem_para_done(result: dict[str, Any]) -> dict[str, Any] | None:
    from apura.capabilities import comprimir_data_url_imagem

    url = (result.get("image_url") or "").strip()
    data = (result.get("image_data_url") or "").strip()
    prompt = ((result.get("itens") or [{}])[0] or {}).get("prompt")
    if url.startswith("http"):
        return {"url": url, "prompt": prompt}
    if data.startswith("data:"):
        data = comprimir_data_url_imagem(data, max_side=1280, max_chars=700_000, quality=75)
        if len(data) < 900_000:
            return {"data_url": data, "prompt": prompt}
        # última tentativa mais agressiva
        data = comprimir_data_url_imagem(data, max_side=960, max_chars=500_000, quality=55)
        if len(data) < 900_000:
            return {"data_url": data, "prompt": prompt}
        return {"omitida": True, "nota": "imagem gerada (ainda grande após compressão)"}
    return None


async def executar_hub(
    historico: list[dict[str, str]],
    mcp_token: str,
    skills_text: str = "",
    modo_narrativa: bool = False,
    campanha_ctx: str = "",
    politica: dict[str, Any] | None = None,
    missao_state: MissaoState | None = None,
    anexos: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Gera eventos SSE: status, token, done, error. Inclui missao_state no done.dados."""
    from apura.perfil_policy import filtrar_mcp_tools, resumo_politica, tool_permitida

    pergunta = _ultima_pergunta(historico)
    slug_pol = (politica or {}).get("perfil_slug") if politica else None
    pol = politica or {
        "bypass": True,
        "tools": set(),
        "modelo_orquestrador": _orchestrator_model("estrategista"),
        "modelo_redator": _writer_model("estrategista"),
        "fonte": "sem_politica",
    }
    state = missao_state or MissaoState(perfil=(pol.get("perfil_slug") or "analista"))
    if pol.get("bypass"):
        # Super gestor: acesso pleno + protocolo Ary disponível
        state.perfil = "estrategista"
    elif pol.get("perfil_slug"):
        from apura.missao_state import perfil_de_slug

        state.perfil = perfil_de_slug(pol.get("perfil_slug")).value

    cmd = detectar_comando(pergunta)
    state = aplicar_comando(state, cmd, pergunta)

    slug = pol.get("perfil_slug") or slug_pol
    orch_model = (pol.get("modelo_orquestrador") or _orchestrator_model(slug)).strip()
    writer_model = (pol.get("modelo_redator") or _writer_model(slug)).strip()
    if state.usa_protocolo_airy:
        orch_model = _ary_orchestrator_model().strip()
        writer_model = _ary_writer_model().strip()
    tools = filtrar_mcp_tools(pol) if not pol.get("bypass") else MCP_TOOLS
    if not tools:
        yield _sse(
            "error",
            {"mensagem": "Seu Perfil não tem tools liberadas. Peça ajuste ao gestor da campanha."},
        )
        return

    # Briefing legado só se ainda estiver nessas etapas (Ativar Ary NÃO entra aqui)
    _etapas_protocolo = {
        "briefing_objetivo",
        "briefing_estilo",
        "briefing_papel",
        "briefing_detalhe",
        "briefing_refs",
        "matriz",
    }
    _pedido_dado = any(
        k in pergunta.lower()
        for k in (
            "vot",
            "eleito",
            "urna",
            "tse",
            "cifra",
            "instagram",
            "@",
            "clima",
            "gasto",
            "pesquis",
            "pdf",
            "mapa",
            "plano",
            "imagem",
            "áudio",
            "audio",
            "anexo",
            "transcrev",
            "capa",
            "banner",
            "flyer",
            "mockup",
            "gerar",
            "arte ",
            "peça",
            "peca",
        )
    )
    so_protocolo = (
        state.usa_protocolo_airy
        and state.etapa in _etapas_protocolo
        and (cmd is not None or not _pedido_dado)
    )
    so_ativacao = cmd in ("ativar", "ativar_criacao", "desativar")
    max_rounds = 16 if state.usa_protocolo_airy else _MAX_TOOL_ROUNDS

    orch_system = SYSTEM_ORCHESTRATOR
    if modo_narrativa or state.perfil == "estrategista":
        orch_system = f"{SYSTEM_ORCHESTRATOR}\n\n{NARRATIVA_ORCHESTRATOR}"
    orch_system = f"{orch_system}\n\n{_system_protocolo(state)}"
    if campanha_ctx.strip():
        orch_system = (
            f"{orch_system}\n\n"
            "Contexto desta campanha (escopo + identidade + memória). "
            "Números oficiais só via tools. Rival = bloco identidade (não ecoar rótulos ao usuário).\n"
            f"{_ctx_para_orquestrador(campanha_ctx)}"
        )
    ax_txt = _resumo_anexos(anexos)
    if ax_txt:
        orch_system = f"{orch_system}\n\n{ax_txt}"
    slug = pol.get("perfil_slug")
    if slug and not pol.get("bypass"):
        orch_system = (
            f"{orch_system}\n\n"
            f"Perfil de acesso: {slug}. Use apenas tools disponíveis."
        )

    tool_log: list[dict[str, Any]] = []
    notas = ""

    try:
        if so_ativacao:
            if cmd == "desativar":
                notas = (
                    "Ary DESATIVADO. Confirme em 1–2 frases o retorno ao modo padrão. "
                    "Sem briefing."
                )
            else:
                notas = (
                    "Ary ATIVADO: modelo robusto + agentes plenos. "
                    "Resposta curta (3–5 linhas): pronta para perguntas complexas; "
                    "usará dados/clima/acervo/web conforme a pergunta. "
                    "NÃO faça briefing. NÃO pergunte objetivo/estilo/papel. Sem inventar cifra."
                )
            yield _sse(
                "status",
                {
                    "fase": "ary",
                    "etapa": state.etapa,
                    "perfil": state.perfil,
                    "modelo": writer_model,
                    "ary": state.protocolo_ativo,
                },
            )
        elif so_protocolo:
            notas = (
                f"PROTOCOLO_LEGADO:\netapa={state.etapa}\ncomando={cmd or 'conteudo'}\n"
                f"aguardando_ok={state.aguardando_ok}\n"
                "Conduza a etapa legada se necessário."
            )
            yield _sse("status", {"fase": "protocolo", "etapa": state.etapa, "perfil": state.perfil})
        else:
            campanha_id = pol.get("campanha_id")
            usuario_id = pol.get("usuario_id")
            pergunta_efetiva = pergunta

            # Áudio anexado = pedido falado: transcreve ANTES do orch e usa como pergunta
            audios = _anexos_audio(anexos)
            if audios and (pol.get("bypass") or tool_permitida(pol, "transcrever_audio")):
                yield _sse("status", {"fase": "consultando", "tool": "transcrever_audio", "motivo": "pedido_falado"})
                args_tx = _injetar_anexo(
                    "transcrever_audio",
                    {
                        "anexo_idx": 0,
                        "pergunta": (
                            "Transcreva fielmente em português BR o que a pessoa disse. "
                            "Se for um pedido/pergunta à campanha, preserve o texto exatamente. "
                            "Não invente."
                        ),
                    },
                    anexos,
                )
                # Prefer first audio anexo explicitly
                a0 = audios[0]
                args_tx["file_base64"] = a0.get("data_base64") or a0.get("file_base64") or args_tx.get("file_base64")
                args_tx["mime"] = a0.get("mime") or args_tx.get("mime")
                args_tx["filename"] = a0.get("nome") or a0.get("filename") or "voz.webm"
                result_tx = await chamar_mcp(
                    "transcrever_audio",
                    args_tx,
                    mcp_token,
                    campanha_id=campanha_id,
                    usuario_id=usuario_id,
                )
                tool_log.append(
                    {
                        "tool": "transcrever_audio",
                        "params": {
                            k: (
                                f"[omitido {len(str(v))} chars]"
                                if k in ("file_base64", "data_base64") and v
                                else v
                            )
                            for k, v in args_tx.items()
                        },
                        "result": _result_para_log(result_tx),
                        "forcado": "pedido_falado",
                    }
                )
                tx = _texto_transcricao(result_tx)
                if tx:
                    if _mensagem_so_anexo_ou_vazia(pergunta):
                        pergunta_efetiva = tx
                    else:
                        pergunta_efetiva = f"{pergunta.strip()}\n\n(Pedido falado):\n{tx}"
                    yield _sse("status", {"fase": "planejando", "transcricao": True})

            orch_messages: list[dict[str, Any]] = [{"role": "system", "content": orch_system}]
            hist_orch = _historico_orquestrador(historico)
            # Substitui última mensagem do user pela pergunta efetiva (transcrição)
            if hist_orch and hist_orch[-1].get("role") == "user" and pergunta_efetiva != pergunta:
                hist_orch = hist_orch[:-1]
                hist_orch.append(
                    {
                        "role": "user",
                        "content": (
                            "Pedido do usuário (áudio já transcrito — NÃO chame transcrever_audio de novo):\n"
                            f"{pergunta_efetiva[:2500]}\n\n"
                            "Responda esse pedido com as tools necessárias (dados, clima, etc.)."
                        ),
                    }
                )
            elif anexos and _mensagem_so_anexo_ou_vazia(pergunta) and not audios:
                hist_orch.append(
                    {
                        "role": "user",
                        "content": "Analise o(s) anexo(s) listados com a tool de mídia adequada.",
                    }
                )
            orch_messages.extend(hist_orch)

            # Usa pergunta efetiva no restante do turno
            pergunta = pergunta_efetiva

            for _ in range(max_rounds):
                yield _sse(
                    "status",
                    {
                        "fase": "planejando",
                        "modelo": orch_model,
                        "perfil": state.perfil,
                        "ary": state.protocolo_ativo,
                    },
                )
                r = await _openrouter(orch_messages, model=orch_model, tools=tools, stream=False)
                if r.status_code >= 400:
                    yield _sse("error", {"mensagem": _erro_openrouter(r.status_code, r.text)})
                    return
                choice = r.json()["choices"][0]["message"]
                tool_calls = choice.get("tool_calls") or []

                if tool_calls:
                    orch_messages.append(_msg_assistant(choice))
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        if name == "consultar_clima":
                            args = _enriquecer_clima_params(args, campanha_ctx, pergunta)
                        args = _injetar_anexo(name, args, anexos)
                        if name in ("gerar_mapa_html", "gerar_plano_html") and campanha_ctx:
                            args.setdefault("contexto_campanha", campanha_ctx[:1500])
                        if name == "gerar_imagem" and campanha_ctx:
                            args.setdefault("contexto_campanha", campanha_ctx[:2500])
                            args.setdefault("resolution", "1K")
                        if not tool_permitida(pol, name):
                            result = {
                                "erro": "tool_negada_pelo_perfil",
                                "tool": name,
                                "perfil": pol.get("perfil_slug"),
                                "mensagem": (
                                    f"Tool '{name}' não permitida no Perfil "
                                    f"{pol.get('perfil_slug') or 'atual'}."
                                ),
                            }
                            tool_log.append({"tool": name, "params": args, "result": result})
                            orch_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": resumir_resultado(result, max_chars=2000),
                                }
                            )
                            continue
                        yield _sse("status", {"fase": "consultando", "tool": name})
                        result = await chamar_mcp(
                            name,
                            args,
                            mcp_token,
                            campanha_id=campanha_id,
                            usuario_id=usuario_id,
                        )
                        # params no log sem base64
                        params_log = {
                            k: (f"[omitido {len(str(v))} chars]" if k in ("file_base64", "data_base64") and v else v)
                            for k, v in args.items()
                        }
                        entry: dict[str, Any] = {
                            "tool": name,
                            "params": params_log,
                            "result": _result_para_log(result),
                        }
                        if name == "gerar_imagem" and isinstance(result, dict):
                            img_done = _imagem_para_done(result)
                            if img_done:
                                entry["_imagem_done"] = img_done
                        tool_log.append(entry)
                        orch_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": resumir_resultado(result, max_chars=6000),
                            }
                        )
                    continue

                notas = _notas_orquestrador(choice.get("content"))
                break
            else:
                yield _sse("error", {"mensagem": "Limite de consultas atingido nesta mensagem."})
                return

            # Playbook duro: estratégia/ângulo sem clima → força consulta no rival
            from apura.agents.engajamento import (
                plano_engajamento_forcado,
                plano_html_forcado,
                plano_imagem_forcado,
                resultado_clima_vazio,
                web_ja_consultada,
            )

            def _ok(name: str) -> bool:
                return bool(pol.get("bypass")) or tool_permitida(pol, name)

            extras_forcados = list(
                plano_engajamento_forcado(pergunta, campanha_ctx, tool_log, tool_ok=_ok)
            )
            extras_forcados.extend(
                plano_imagem_forcado(pergunta, campanha_ctx, tool_log, tool_ok=_ok)
            )
            extras_forcados.extend(
                plano_html_forcado(pergunta, campanha_ctx, tool_log, tool_ok=_ok)
            )

            for extra in extras_forcados:
                name = extra["tool"]
                args = dict(extra.get("params") or {})
                if name == "consultar_clima":
                    args = _enriquecer_clima_params(args, campanha_ctx, pergunta)
                yield _sse(
                    "status",
                    {
                        "fase": "consultando",
                        "tool": name,
                        "motivo": extra.get("motivo"),
                    },
                )
                result = await chamar_mcp(
                    name,
                    args,
                    mcp_token,
                    campanha_id=campanha_id,
                    usuario_id=usuario_id,
                )
                entry: dict[str, Any] = {
                    "tool": name,
                    "params": {
                        k: (
                            f"[omitido {len(str(v))} chars]"
                            if k in ("file_base64", "data_base64") and v
                            else v
                        )
                        for k, v in args.items()
                    },
                    "result": _result_para_log(result),
                    "forcado": extra.get("motivo"),
                }
                if name == "gerar_imagem" and isinstance(result, dict):
                    img_done = _imagem_para_done(result)
                    if img_done:
                        entry["_imagem_done"] = img_done
                tool_log.append(entry)

            # Se clima forçado veio vazio e ainda não há web → Perplexity
            if (
                _ok("pesquisar_web")
                and not web_ja_consultada(tool_log)
                and resultado_clima_vazio(tool_log)
                and any(t.get("forcado") for t in tool_log)
            ):
                from apura.agents.engajamento import rival_principal_do_ctx, nosso_do_ctx

                alvo = rival_principal_do_ctx(campanha_ctx) or nosso_do_ctx(campanha_ctx)
                if alvo:
                    args = {"query": f"{alvo} eleições notícias pesquisa intenção de voto"}
                    yield _sse(
                        "status",
                        {
                            "fase": "consultando",
                            "tool": "pesquisar_web",
                            "motivo": "playbook_clima_vazio_web",
                        },
                    )
                    result = await chamar_mcp(
                        "pesquisar_web",
                        args,
                        mcp_token,
                        campanha_id=campanha_id,
                        usuario_id=usuario_id,
                    )
                    tool_log.append(
                        {
                            "tool": "pesquisar_web",
                            "params": args,
                            "result": _result_para_log(result),
                            "forcado": "playbook_clima_vazio_web",
                        }
                    )

        state.agentes_plano = plano_de_tool_log(tool_log)
        yield _sse(
            "status",
            {"fase": "redigindo", "modelo": writer_model, "ary": state.protocolo_ativo},
        )
        writer_messages = [
            {"role": "system", "content": _system_redator(skills_text, campanha_ctx, state)},
            {
                "role": "user",
                "content": _entrada_redator(pergunta, historico, tool_log, notas, state),
            },
        ]
        full_parts: list[str] = []
        async for token in _stream_resposta(writer_model, writer_messages):
            full_parts.append(token)
            yield _sse("token", {"text": token})
        full = "".join(full_parts)

        # Se redator produziu matriz em markdown list, tenta capturar
        if state.etapa == "matriz" and full:
            bullets = re.findall(r"^\s*[-*]\s+(.+)$", full, re.M)
            if len(bullets) >= 2:
                state.matriz = [b.strip()[:200] for b in bullets[:30]]

        dados: dict[str, Any] = {
            "politica": resumo_politica(pol),
            "missao_state": state.to_dict(),
            "agentes": state.agentes_plano,
            "ary_ativo": state.protocolo_ativo,
            "modelos": {"orquestrador": orch_model, "redator": writer_model},
        }
        if tool_log:
            dados["tool_results"] = tool_log
        done: dict[str, Any] = {"conteudo": full, "dados": dados}
        if _pediu_relatorio_html(pergunta) and tool_log:
            titulo = pergunta[:80] or "Relatório Apura"
            done["relatorio_html"] = exportar_html(dados, full, titulo)
        # Artefatos visuais das tools
        for tr in tool_log:
            tool_name = tr.get("tool")
            res = tr.get("result") if isinstance(tr.get("result"), dict) else None
            if not res:
                continue
            if tool_name in ("gerar_mapa_html", "gerar_plano_html"):
                html = res.get("html")
                if html:
                    done["mapa_html"] = html
                    dados["mapa_html"] = html
            if tool_name == "gerar_imagem":
                # result no log já omitiu data_url — re-ler do raw não dá; guardar no SSE
                # Hub precisa do result original. Guardamos side-channel em tr["_imagem"]
                pass
        # Reextrai imagem do tool_log se ainda houver url http; data_url vem de side-channel
        for tr in tool_log:
            if tr.get("tool") != "gerar_imagem":
                continue
            side = tr.get("_imagem_done")
            if isinstance(side, dict):
                done["imagem"] = side
                dados["imagem"] = side
                break
            res = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            img = _imagem_para_done(res)  # type: ignore[arg-type]
            if img:
                done["imagem"] = img
                dados["imagem"] = img
                break
        yield _sse("done", done)

    except RuntimeError as exc:
        yield _sse("error", {"mensagem": str(exc)})
    except Exception as exc:
        yield _sse("error", {"mensagem": f"Falha no hub Apura: {exc}"})
