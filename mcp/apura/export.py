"""Exportação XLSX e HTML a partir dos dados das consultas."""
from __future__ import annotations

import html as html_module
import io
import json
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter


def _linhas_de_dados(dados: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not dados:
        return []
    out: list[dict[str, Any]] = []
    for tr in dados.get("tool_results", []):
        res = tr.get("result")
        if not isinstance(res, dict):
            continue
        linhas = res.get("linhas")
        if isinstance(linhas, list):
            for row in linhas:
                if isinstance(row, dict):
                    row = dict(row)
                    row["_consulta"] = tr.get("tool", "")
                    out.append(row)
    return out


def exportar_xlsx(dados: dict[str, Any] | None, titulo: str = "Apura") -> bytes:
    rows = _linhas_de_dados(dados)
    wb = Workbook()
    ws = wb.active
    ws.title = "Dados"
    if not rows:
        ws.append(["Sem dados tabulares nesta resposta"])
    else:
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
    meta = wb.create_sheet("Meta")
    meta.append(["titulo", titulo])
    meta.append(["gerado_em", datetime.now(timezone.utc).isoformat()])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_html(
    dados: dict[str, Any] | None,
    conteudo_md: str,
    titulo: str = "Apura · Relatório",
) -> str:
    rows = _linhas_de_dados(dados)
    esc = html_module.escape
    parts = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        f"<title>{esc(titulo)}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#0c1222;line-height:1.6}",
        "h1{font-size:1.6rem;color:#0d4f4a;border-bottom:2px solid #e6f4f2;padding-bottom:12px}",
        "h2{font-size:1.1rem;color:#0d4f4a;margin:28px 0 12px}",
        "table{border-collapse:collapse;width:100%;margin:16px 0;font-size:0.88rem}",
        "th,td{border:1px solid #e2e8f0;padding:8px 10px;text-align:left}",
        "th{background:#e6f4f2;position:sticky;top:0}",
        "tr:nth-child(even){background:#f8fafc}",
        ".prose{line-height:1.65;color:#334155;white-space:pre-wrap;margin:20px 0}",
        ".meta{color:#64748b;font-size:0.85rem;margin-top:32px}",
        "</style></head><body>",
        f"<h1>{esc(titulo)}</h1>",
        f"<p class='prose'>{esc(conteudo_md)}</p>",
    ]
    if rows:
        parts.append("<h2>Dados consultados</h2>")
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
    parts.append(f"<p><small>Gerado em {esc(datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC'))}</small></p>")
    parts.append("</body></html>")
    return "".join(parts)
