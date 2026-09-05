"""DDL Mapa Apura — patch_mapa.sql."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

_SQL_DIRS = [
    Path(__file__).resolve().parents[1] / "sql",
    Path(__file__).resolve().parents[2] / "sql",
]
_READY = False


def _ddl_url() -> str | None:
    return (
        os.environ.get("POSTGRES_ADMIN_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("AGENTE_DATABASE_URL")
    )


def _find_sql(name: str) -> Path | None:
    for d in _SQL_DIRS:
        p = d / name
        if p.exists():
            return p
    return None


def ensure_schema() -> None:
    global _READY
    if _READY:
        return
    url = _ddl_url()
    if not url:
        raise RuntimeError("Banco indisponível")
    patch = _find_sql("patch_mapa.sql")
    if not patch:
        raise RuntimeError("patch_mapa.sql ausente")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch.read_text(encoding="utf-8"))
    _READY = True
