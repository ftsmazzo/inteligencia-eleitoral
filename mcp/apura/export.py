"""Exportação XLSX e HTML a partir dos dados das consultas (Fato / Acervo / Clima)."""
from __future__ import annotations

import html as html_module
import io
import json
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter


def _flatten_rows(res: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    linhas = res.get("linhas")
    if isinstance(linhas, list):
        for row in linhas:
            if isinstance(row, dict):
                r = dict(row)
                r["_consulta"] = tool
                rows.append(r)
    itens = res.get("itens")
    if isinstance(itens, list):
        for row in itens:
            if isinstance(row, dict):
                r = dict(row)
                r["_consulta"] = tool
                rows.append(r)
    series = res.get("series")
    if isinstance(series, list):
        for block in series:
            if not isinstance(block, dict):
                continue
            ano = block.get("ano")
            for row in block.get("linhas") or []:
                if isinstance(row, dict):
                    r = dict(row)
                    r["_consulta"] = tool
                    r["_ano_serie"] = ano
                    rows.append(r)
    for key in ("acervo_a", "acervo_b"):
        sub = res.get(key)
        if isinstance(sub, dict):
            for row in sub.get("itens") or []:
                if isinstance(row, dict):
                    r = dict(row)
                    r["_consulta"] = f"{tool}:{key}"
                    rows.append(r)
    return rows


def _classificar_tool(tool: str) -> str:
    t = (tool or "").lower()
    if "acervo" in t or "ficha" in t:
        return "acervo"
    if "clima" in t:
        return "clima"
    return "fato"


def _linhas_por_camada(dados: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"fato": [], "acervo": [], "clima": []}
    if not dados:
        return out
    for tr in dados.get("tool_results", []):
        tool = tr.get("tool", "")
        res = tr.get("result")
        if not isinstance(res, dict):
            continue
        camada = _classificar_tool(tool)
        out[camada].extend(_flatten_rows(res, tool))
    return out


def _sheet_from_rows(ws, rows: list[dict[str, Any]], titulo_vazio: str) -> None:
    if not rows:
        ws.append([titulo_vazio])
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    ws.append(keys)
    for row in rows:
        ws.append([row.get(k, "") for k in keys])
    for i, _ in enumerate(keys, 1):
        ws.column_dimensions[get_column_letter(i)].width = 18


def exportar_xlsx(dados: dict[str, Any] | None, titulo: str = "Apura") -> bytes:
    camadas = _linhas_por_camada(dados)
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "Fato"
    _sheet_from_rows(ws0, camadas["fato"], "Sem dados tabulares de urna/contexto nesta resposta")

    ws1 = wb.create_sheet("Acervo")
    _sheet_from_rows(ws1, camadas["acervo"], "Sem trechos de acervo nesta resposta")

    ws2 = wb.create_sheet("Clima")
    _sheet_from_rows(ws2, camadas["clima"], "Sem itens de clima nesta resposta")

    meta = wb.create_sheet("Meta")
    meta.append(["titulo", titulo])
    meta.append(["gerado_em", datetime.now(timezone.utc).isoformat()])
    meta.append(["fato_linhas", len(camadas["fato"])])
    meta.append(["acervo_linhas", len(camadas["acervo"])])
    meta.append(["clima_linhas", len(camadas["clima"])])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_html(
    dados: dict[str, Any] | None,
    conteudo_md: str,
    titulo: str = "Apura · Relatório",
) -> str:
    camadas = _linhas_por_camada(dados)
    esc = html_module.escape
    parts = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        f"<title>{esc(titulo)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#0c1222;line-height:1.6}",
        "h1{font-size:1.6rem;color:#0d4f4a;border-bottom:2px solid #e6f4f2;padding-bottom:12px}",
        "h2{font-size:1.1rem;color:#0d4f4a;margin:28px 0 12px}",
        "h3{font-size:0.95rem;color:#64748b;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.04em}",
        "table{border-collapse:collapse;width:100%;margin:16px 0;font-size:0.88rem}",
        "th,td{border:1px solid #e2e8f0;padding:8px 10px;text-align:left;vertical-align:top}",
        "th{background:#e6f4f2}",
        "tr:nth-child(even){background:#f8fafc}",
        ".prose{line-height:1.65;color:#334155;white-space:pre-wrap;margin:20px 0}",
        ".badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.75rem;font-weight:600;margin-right:6px}",
        ".badge-fato{background:#dbeafe;color:#1e40af}",
        ".badge-acervo{background:#fef3c7;color:#92400e}",
        ".badge-clima{background:#fce7f3;color:#9d174d}",
        ".meta{color:#64748b;font-size:0.85rem;margin-top:32px}",
        "</style></head><body>",
        f"<h1>{esc(titulo)}</h1>",
        "<p><span class='badge badge-fato'>Fato</span><span class='badge badge-acervo'>Acervo</span>"
        "<span class='badge badge-clima'>Clima</span></p>",
        f"<div class='prose'>{esc(conteudo_md)}</div>",
    ]

    for label, key, badge in (
        ("Dados oficiais (urna / contexto)", "fato", "badge-fato"),
        ("Acervo (programas / fichas)", "acervo", "badge-acervo"),
        ("Clima (indício)", "clima", "badge-clima"),
    ):
        rows = camadas[key]
        if not rows:
            continue
        parts.append(f"<h2><span class='badge {badge}'>{label.split()[0]}</span> {esc(label)}</h2>")
        keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        parts.append("<table><thead><tr>")
        parts.extend(f"<th>{esc(k)}</th>" for k in keys)
        parts.append("</tr></thead><tbody>")
        for row in rows:
            parts.append("<tr>")
            parts.extend(f"<td>{esc(str(row.get(k, '')))}</td>" for k in keys)
            parts.append("</tr>")
        parts.append("</tbody></table>")

    parts.append(f"<p class='meta'>Gerado em {esc(datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC'))} · Inteligência Eleitoral Brasil</p>")
    parts.append("</body></html>")
    return "".join(parts)
