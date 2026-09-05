"""Compactação de tool_log em camadas Fato / Indício / etc. para o redator."""
from __future__ import annotations

import json
from typing import Any

from apura.agents.registry import camada_da_tool
from apura.mcp_client import resumir_resultado


def _blob_resultado(res: Any) -> str:
    if not isinstance(res, dict):
        return str(res)[:1500]
    status = res.get("status", "")
    if status == "fora_do_recorte":
        return f"status: fora_do_recorte | {res.get('mensagem', '')}"
    if status == "vazio":
        msg = res.get("mensagem") or "sem itens neste recorte/filtro"
        nota = res.get("nota_metodologica") or ""
        return f"status: vazio | {msg}" + (f"\nnota: {nota}" if nota else "")
    nota = res.get("nota_metodologica") or res.get("mensagem") or ""
    partes = [f"nota: {nota}"] if nota else []
    for key in ("linhas", "itens", "series"):
        if isinstance(res.get(key), list):
            partes.append(json.dumps(res[key], ensure_ascii=False, default=str)[:6000])
            break
    else:
        if res.get("acervo_a") or res.get("acervo_b") or res.get("html") or res.get("url_imagem"):
            partes.append(resumir_resultado(res, max_chars=6000))
        else:
            partes.append(resumir_resultado(res, max_chars=6000))
    return "\n".join(partes)


def compactar_por_camadas(tool_log: list[dict[str, Any]]) -> str:
    if not tool_log:
        return "(Nenhuma consulta nesta rodada.)"
    buckets: dict[str, list[str]] = {}
    for tr in tool_log:
        tool = tr.get("tool") or "?"
        camada = camada_da_tool(tool)
        header = f"## [{camada}] {tool} — params: {json.dumps(tr.get('params', {}), ensure_ascii=False)}"
        buckets.setdefault(camada, []).append(header + "\n" + _blob_resultado(tr.get("result")))

    ordem = [
        "fato",
        "acervo",
        "indicio_clima",
        "indicio_web",
        "indicio_media",
        "artefato_visual",
        "operacional",
    ]
    titulos = {
        "fato": "### CAMADA FATO (oficial)",
        "acervo": "### CAMADA ACERVO / PROGRAMA",
        "indicio_clima": "### CAMADA CLIMA (indício — Apify/news)",
        "indicio_web": "### CAMADA WEB (indício)",
        "indicio_media": "### CAMADA MÍDIA (indício)",
        "artefato_visual": "### CAMADA VISUAL (artefato gerado)",
        "operacional": "### CAMADA OPERACIONAL",
    }
    out: list[str] = []
    for c in ordem:
        if c not in buckets:
            continue
        out.append(titulos[c])
        out.extend(buckets[c])
    for c, parts in buckets.items():
        if c in ordem:
            continue
        out.append(f"### CAMADA {c}")
        out.extend(parts)
    return "\n\n".join(out)
