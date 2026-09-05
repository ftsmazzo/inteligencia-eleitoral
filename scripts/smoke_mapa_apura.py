#!/usr/bin/env python3
"""Smoke estático · módulo Mapa Apura."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))


def main() -> int:
    from mapa.routes import router
    from mapa.store import listar_municipios  # noqa: F401

    paths = {getattr(r, "path", None) for r in router.routes}
    need = {
        "/municipios",
        "/notas",
        "/notas/{cod_ibge}",
        "/caravanas",
        "/caravanas/{caravana_id}",
    }
    # FastAPI may store full prefix
    joined = " ".join(str(p) for p in paths)
    for n in ("municipios", "notas", "caravanas"):
        if n not in joined:
            print("FAIL rota ausente:", n)
            return 1

    sql = (ROOT / "sql" / "patch_mapa.sql").read_text(encoding="utf-8")
    if "1600303" not in sql or "Macapá" not in sql:
        print("FAIL seed Macapá ausente")
        return 1
    if "ctl.mapa_nota" not in sql or "ctl.mapa_caravana" not in sql:
        print("FAIL tabelas ausentes no patch")
        return 1

    idx = (ROOT / "mcp" / "static" / "apura" / "index.html").read_text(encoding="utf-8")
    for token in ("btn-view-mapa", "mapa-view", "loadMapa", "leaflet", "ap-municipios.geojson", "MAPA_AP_BOUNDS"):
        if token not in idx and token != "ap-municipios.geojson":
            # geojson is referenced as path; check file separately
            if token not in idx:
                print("FAIL UI ausente:", token)
                return 1
    geo = ROOT / "mcp" / "static" / "apura" / "assets" / "ap-municipios.geojson"
    if not geo.exists():
        print("FAIL geojson ausente")
        return 1
    import json
    fc = json.loads(geo.read_text(encoding="utf-8"))
    if len(fc.get("features") or []) != 16:
        print("FAIL geojson deve ter 16 municipios")
        return 1

    print("OK smoke_mapa_apura")
    print("  rotas mapa + seed AP 16 mun + UI Leaflet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
