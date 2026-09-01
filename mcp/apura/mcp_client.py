"""Cliente HTTP interno para o MCP — com expansão de partido/região."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from apura.partidos import eh_regiao, siglas_equivalentes, ufs_da_regiao
from apura.recorte import normalizar_params_mcp
from apura.tools import TOOL_TO_MCP


def _base_url() -> str:
    return os.environ.get("MCP_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")


async def _post_mcp(method: str, params: dict[str, Any], mcp_token: str) -> Any:
    body = {"method": method, "params": params}
    if method == "catalogo":
        body["params"] = {}
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{_base_url()}/mcp",
            json=body,
            headers={"Authorization": f"Bearer {mcp_token}"},
        )
        if r.status_code >= 400:
            return {"erro": r.text, "status": r.status_code}
        return r.json()


def _merge_resultados(
    resultados: list[Any],
    *,
    nota_extra: str,
    ufs_esperadas: list[str] | None = None,
) -> dict[str, Any]:
    linhas: list[Any] = []
    notas: list[str] = []
    status = "vazio"
    for res in resultados:
        if not isinstance(res, dict):
            continue
        if res.get("erro"):
            continue
        if res.get("status") == "ok":
            status = "ok"
        if res.get("nota_metodologica"):
            notas.append(str(res["nota_metodologica"]))
        for row in res.get("linhas") or []:
            linhas.append(row)
    seen: set[str] = set()
    uniq: list[Any] = []
    for row in linhas:
        if not isinstance(row, dict):
            uniq.append(row)
            continue
        key = f"{row.get('ano')}|{row.get('sq_candidato')}|{row.get('sg_partido')}|{row.get('sg_uf')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)

    ufs_com_dado = {str(r.get("sg_uf")) for r in uniq if isinstance(r, dict) and r.get("sg_uf")}
    zeros = [u for u in (ufs_esperadas or []) if u not in ufs_com_dado]
    if zeros:
        notas.append("UFs com zero eleitos neste filtro: " + ",".join(zeros))

    out: dict[str, Any] = {
        "status": status if uniq else "vazio",
        "mensagem": None if uniq else "Zero eleitos neste recorte (filtro expandido; base existe).",
        "linhas": uniq,
        "nota_metodologica": " | ".join(dict.fromkeys([*notas, nota_extra])),
        "ufs_consultadas": ufs_esperadas or sorted(ufs_com_dado),
        "ufs_com_zero": zeros,
    }
    return out


async def chamar_mcp(tool_name: str, params: dict[str, Any], mcp_token: str) -> Any:
    method = TOOL_TO_MCP.get(tool_name)
    if not method:
        return {"erro": f"tool desconhecida: {tool_name}"}

    params = dict(params or {})
    params, nota_recorte = normalizar_params_mcp(method, params)
    uf = params.get("uf")
    partido = params.get("sg_partido")

    # Região → 1 call se a API expandir; senão fan-out por UF
    ufs: list[str | None]
    if eh_regiao(uf):
        ufs = ufs_da_regiao(uf)
        regiao_label = str(uf).strip().upper()
    else:
        ufs = [uf]
        regiao_label = None

    siglas = siglas_equivalentes(partido) if partido else [None]
    # Preferir 1 call com região/partido (API SQL faz a expansão). Fan-out só se região.
    if regiao_label and method in ("eleitos", "nominata", "votacao", "comparecimento"):
        # Uma call por UF (API já expande partido); evita limite 500 e omissão
        jobs = []
        for u in ufs:
            p = dict(params)
            p["uf"] = u
            if partido:
                p["sg_partido"] = partido  # API expande; sem fan-out de sigla
            if method == "eleitos":
                p["limite"] = min(int(p.get("limite") or 50), 50)
            jobs.append(_post_mcp(method, p, mcp_token))
        resultados = await asyncio.gather(*jobs)
        nota = f"expansão automática região={regiao_label} UFs={','.join(ufs)}"
        if partido and len(siglas) > 1:
            nota += f" | partido pedido={partido} equivalentes={','.join(siglas)} (API)"
        if nota_recorte:
            nota += f" | {nota_recorte}"
        return _merge_resultados(list(resultados), nota_extra=nota, ufs_esperadas=list(ufs))

    # Sem região: 1 call (partido expandido no SQL)
    res = await _post_mcp(method, params, mcp_token)
    if nota_recorte and isinstance(res, dict):
        prev = res.get("nota_metodologica") or ""
        res["nota_metodologica"] = " | ".join(x for x in (prev, nota_recorte) if x)
    return res


def resumir_resultado(result: Any, max_chars: int = 12000) -> str:
    # Remove url_raw monstro antes de mandar ao redator (evita colar no chat).
    if isinstance(result, dict) and isinstance(result.get("itens"), list):
        limpo = dict(result)
        itens = []
        for it in limpo["itens"]:
            if isinstance(it, dict):
                it = {k: v for k, v in it.items() if k != "url_raw"}
            itens.append(it)
        limpo["itens"] = itens
        result = limpo
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "… [truncado]"
