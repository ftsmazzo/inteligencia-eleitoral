"""Lista candidatos via api.nominata + documento canônico (sq)."""
from __future__ import annotations

from typing import Any

import psycopg

from gestao import documento
from gestao.store import CARGOS


def _cargo_key(cd_cargo: int) -> str | None:
    for c in CARGOS:
        if c["cd_cargo"] == cd_cargo:
            return c["key"]
    return None


def _rank(q: str | None, ln: dict[str, Any]) -> tuple:
    """Prioriza bate-exato de urna / início do nome — evita Cley no lugar de Clécio."""
    qq = (q or "").strip().upper()
    urna = (ln.get("nm_urna") or "").upper()
    civil = (ln.get("nm_candidato") or "").upper()
    if not qq:
        return (1, urna)
    if urna == qq or civil == qq:
        return (0, urna)
    if urna.startswith(qq) or civil.startswith(qq):
        return (0, urna)
    if qq in urna or qq in civil:
        return (1, urna)
    return (2, urna)


def listar_candidatos(
    conn: psycopg.Connection,
    *,
    ano: int,
    cargo: str | int,
    uf: str,
    q: str | None = None,
    limite: int = 200,
) -> dict[str, Any]:
    if isinstance(cargo, int):
        key = _cargo_key(cargo)
        if not key:
            return {"status": "vazio", "mensagem": "Cargo inválido", "linhas": []}
        cargo_txt = key
        cd = cargo
    else:
        cargo_txt = str(cargo).strip().lower().replace(" ", "_")
        cd = next((c["cd_cargo"] for c in CARGOS if c["key"] == cargo_txt or c["label"].lower() == cargo_txt), None)
        if cd is None:
            aliases = {
                "governador": "governador",
                "senador": "senador",
                "deputado federal": "deputado_federal",
                "deputado estadual": "deputado_estadual",
                "presidente": "presidente",
            }
            cargo_txt = aliases.get(cargo_txt.replace("_", " "), cargo_txt)
        else:
            cargo_txt = _cargo_key(cd) or cargo_txt

    uf = (uf or "").strip().upper()
    lim = max(1, min(int(limite or 200), 500))
    nm = (q or "").strip() or None
    uf_param = None if (not uf or uf == "BR") else uf

    row = conn.execute(
        "SELECT api.nominata(%s::smallint, %s, %s, NULL, NULL, NULL, NULL, %s, %s)",
        (ano, cargo_txt.replace("_", " "), uf_param, nm, lim),
    ).fetchone()
    data = row[0] if row else {"status": "vazio", "linhas": []}
    if isinstance(data, str):
        import json

        data = json.loads(data)
    linhas = data.get("linhas") or []
    if isinstance(linhas, str):
        import json

        linhas = json.loads(linhas)
    out = []
    for ln in linhas:
        if not isinstance(ln, dict):
            continue
        base = {
            "ano": ln.get("ano"),
            "cd_cargo": ln.get("cd_cargo"),
            "sg_uf": ln.get("sg_uf"),
            "sq_candidato": ln.get("sq_candidato"),
            "nr_candidato": ln.get("nr_candidato"),
            "nm_urna": ln.get("nm_urna"),
            "nm_candidato": ln.get("nm_candidato"),
            "sg_partido": ln.get("sg_partido"),
            "ds_situacao": ln.get("ds_situacao"),
        }
        try:
            out.append(documento.enriquecer_linha(conn, base, ano=ano))
        except Exception:
            out.append(base)
    out.sort(key=lambda ln: _rank(nm, ln))
    return {
        "status": data.get("status") or ("ok" if out else "vazio"),
        "mensagem": data.get("mensagem"),
        "linhas": out,
        "total": len(out),
        "nota": "Cada linha é o documento TSE (sq). Nome de urna parecido ≠ mesma pessoa — confira nome completo e partido.",
    }
