"""DDL Mapa Apura — patch_mapa.sql (serializado; sem deadlock em boot paralelo)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import psycopg

_SQL_DIRS = [
    Path(__file__).resolve().parents[1] / "sql",
    Path(__file__).resolve().parents[2] / "sql",
]
_READY = False
_LOCK = threading.Lock()
# Lock de sessão Postgres (único entre workers / requests)
_ADVISORY_KEY = 87423016


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


def _run_sql_script(conn: psycopg.Connection, text: str) -> None:
    """Executa script multi-statement (1 comando por execute)."""
    stmts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in text.splitlines():
        if not in_dollar and line.strip().startswith("--"):
            continue
        parts = line.split("$$")
        if len(parts) > 1 and (len(parts) - 1) % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            buf = []
            if stmt:
                stmts.append(stmt)
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    for stmt in stmts:
        conn.execute(stmt)


def _schema_ok(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        """
        SELECT
          to_regclass('ctl.municipio_geo') IS NOT NULL
          AND to_regclass('ctl.mapa_nota') IS NOT NULL
          AND to_regclass('ctl.mapa_caravana') IS NOT NULL
        """
    ).fetchone()
    return bool(row and row[0])


def ensure_schema() -> None:
    global _READY
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        url = _ddl_url()
        if not url:
            raise RuntimeError("Banco indisponível")
        patch = _find_sql("patch_mapa.sql")
        if not patch:
            raise RuntimeError("patch_mapa.sql ausente")
        sql = patch.read_text(encoding="utf-8")
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                with psycopg.connect(url, autocommit=True) as conn:
                    conn.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_KEY,))
                    try:
                        if _schema_ok(conn):
                            # Já provisionado: seed/módulo ainda podem faltar → patch idempotente leve
                            _run_sql_script(conn, sql)
                        else:
                            _run_sql_script(conn, sql)
                    finally:
                        conn.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_KEY,))
                _READY = True
                return
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "deadlock" in msg or "lock" in msg:
                    time.sleep(0.15 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"Falha ao preparar Mapa após retries: {last_exc}") from last_exc
