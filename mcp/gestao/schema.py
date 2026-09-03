"""DDL Gestão — apply patch_gestao.sql."""
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
    patch_apura = _find_sql("patch_apura.sql")
    patch_gestao = _find_sql("patch_gestao.sql")
    if not patch_gestao:
        raise RuntimeError("Schema Gestão indisponível")
    with psycopg.connect(url, autocommit=True) as conn:
        if patch_apura:
            conn.execute(patch_apura.read_text(encoding="utf-8"))
        conn.execute(patch_gestao.read_text(encoding="utf-8"))
    _READY = True
