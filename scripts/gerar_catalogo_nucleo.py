"""Gera docs/catalogo_nucleo.json a partir da spec + auditoria + api.catalogo."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tse_util import dsn, load_env  # noqa: E402

OUT = ROOT / "docs" / "catalogo_nucleo.json"


def audit_json() -> dict:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "auditar_recorte.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if r.returncode not in (0, 1) and not r.stdout.strip():
        return {"nucleus_ok": None, "checks": [], "erro": r.stderr[:500]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"nucleus_ok": None, "checks": [], "erro": "auditoria indisponível"}


def catalogo_db() -> dict:
    import psycopg

    load_env()
    with psycopg.connect(dsn()) as c:
        cat = c.execute("SELECT api.catalogo()").fetchone()[0]
        ind = c.execute(
            "SELECT id_indicador, nome_exato, unidade, nao_confundir_com FROM ref.dicionario_indicador ORDER BY 1"
        ).fetchall()
    return {
        "mcp": cat,
        "indicadores": [
            {"id": a, "nome": b, "unidade": c, "nao_confundir_com": d} for a, b, c, d in ind
        ],
    }


def main() -> None:
    aud = audit_json()
    try:
        db = catalogo_db()
    except Exception as e:
        db = {"mcp": None, "indicadores": [], "erro_db": str(e)[:300]}

    doc = {
        "produto": "Inteligência Eleitoral Brasil",
        "versao": "0.2",
        "gerado_em": date.today().isoformat(),
        "spec": "docs/SPEC-BRASIL.md",
        "fontes": "docs/FONTES-NUCLEO.md",
        "recorte": {
            "territorio": "Brasil (27 UF + DF)",
            "cargos": "presidente a vereador",
            "urnas_gerais": [2014, 2018, 2022],
            "urnas_municipais": [2016, 2020, 2024],
            "candidatura_viva": 2026,
        },
        "nucleo_eleitoral_ok": aud.get("nucleus_ok"),
        "auditoria_falhas": aud.get("falhas", 0),
        "pacotes_mcp": (db.get("mcp") or {}).get("pacotes"),
        "indicadores": db.get("indicadores"),
        "fora_por_spec": [
            "urna 2026 resultado até apuração oficial",
            "população 2023/2026 sem publicação IBGE",
            "rede_social e complementar TSE (opcional FONTES §2)",
            "trilha B clipping",
            "catálogo NE9 Arquitetura/",
        ],
        "parlamento_parcial": [
            "Senado: votos/proposições sem dump anual",
            "de-para SF revisado na carga",
        ],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ok", OUT, "nucleo", aud.get("nucleus_ok"))


if __name__ == "__main__":
    main()
