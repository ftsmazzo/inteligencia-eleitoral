"""DDL Radar — apply patch_radar.sql (+ v2/v3)."""
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


def _run_sql_script(conn: psycopg.Connection, text: str) -> None:
    """Executa script SQL multi-statement (psycopg.execute = 1 comando)."""
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


def ensure_keywords_column(conn: psycopg.Connection) -> bool:
    """Garante ctl.radar_eixo.keywords. Retorna True se a coluna existe.

    ALTER roda em conexão autocommit separada — se falhar, não aborta a
    transação da request (causa clássica de erro em cascata no Postgres).
    """
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'ctl'
              AND table_name = 'radar_eixo'
              AND column_name = 'keywords'
            """
        ).fetchone()
        if row:
            return True
    except Exception:
        return False

    url = _ddl_url()
    if url:
        try:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(
                    """
                    ALTER TABLE ctl.radar_eixo
                      ADD COLUMN IF NOT EXISTS keywords text NOT NULL DEFAULT ''
                    """
                )
        except Exception:
            pass

    try:
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'ctl'
              AND table_name = 'radar_eixo'
              AND column_name = 'keywords'
            """
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def ensure_excluido_table(conn: psycopg.Connection) -> bool:
    """Garante ctl.radar_alvo_excluido (lista de bloqueio: alvo apagado não volta no seed)."""
    try:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ctl' AND table_name = 'radar_alvo_excluido'
            """
        ).fetchone()
        if row:
            return True
    except Exception:
        return False

    url = _ddl_url()
    if url:
        try:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ctl.radar_alvo_excluido (
                      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                      campanha_id uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
                      chave text NOT NULL,
                      criado_em timestamptz NOT NULL DEFAULT now(),
                      UNIQUE (campanha_id, chave)
                    )
                    """
                )
                admin.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.radar_alvo_excluido TO agente"
                )
        except Exception:
            pass

    try:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ctl' AND table_name = 'radar_alvo_excluido'
            """
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def ensure_schema() -> None:
    global _READY
    if _READY:
        # Mesmo após ready, tenta keywords/excluido (migração pode ter falhado no boot).
        url = _ddl_url()
        if url:
            try:
                with psycopg.connect(url, autocommit=True) as conn:
                    ensure_keywords_column(conn)
                    ensure_excluido_table(conn)
            except Exception:
                pass
        return
    url = _ddl_url()
    if not url:
        raise RuntimeError("Banco indisponível")
    patch_apura = _find_sql("patch_apura.sql")
    patch_radar = _find_sql("patch_radar.sql")
    patch_v2 = _find_sql("patch_radar_v2.sql")
    patch_v3 = _find_sql("patch_radar_v3.sql")
    patch_v4 = _find_sql("patch_radar_v4.sql")
    if not patch_radar:
        raise RuntimeError("Schema Radar indisponível")
    with psycopg.connect(url, autocommit=True) as conn:
        if patch_apura:
            _run_sql_script(conn, patch_apura.read_text(encoding="utf-8"))
        _run_sql_script(conn, patch_radar.read_text(encoding="utf-8"))
        if patch_v2:
            _run_sql_script(conn, patch_v2.read_text(encoding="utf-8"))
        if patch_v3:
            try:
                _run_sql_script(conn, patch_v3.read_text(encoding="utf-8"))
            except Exception:
                pass
        if patch_v4:
            try:
                _run_sql_script(conn, patch_v4.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Hard guarantee — single statement (causa do UndefinedColumn em prod)
        ensure_keywords_column(conn)
        ensure_excluido_table(conn)
    _READY = True
