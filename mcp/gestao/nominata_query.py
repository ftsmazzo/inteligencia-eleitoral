"""Lista candidatos via api.nominata (sem HTTP externo)."""
from __future__ import annotations

from typing import Any

import psycopg

from gestao.store import CARGOS


def _cargo_key(cd_cargo: int) -> str | None:
    for c in CARGOS:
        if c["cd_cargo"] == cd_cargo:
            return c["key"]
    return None


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
            # aceitar nomes TSE comuns
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
        out.append(
            {
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
        )
    return {
        "status": data.get("status") or ("ok" if out else "vazio"),
        "mensagem": data.get("mensagem"),
        "linhas": out,
        "total": len(out),
    }
