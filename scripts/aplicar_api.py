"""Aplica sql/api.sql e cria role agente (só EXECUTE em api)."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, dsn, load_env
import os


def ensure_agente_password() -> str:
    load_env()
    p = os.environ.get("AGENTE_PASSWORD")
    if p:
        return p
    p = secrets.token_urlsafe(24)
    with (ROOT / ".env").open("a", encoding="utf-8") as f:
        f.write(f"\nAGENTE_PASSWORD={p}\n")
    os.environ["AGENTE_PASSWORD"] = p
    return p


def main() -> None:
    sql = (ROOT / "sql" / "api.sql").read_text(encoding="utf-8")
    pwd = ensure_agente_password()
    with psycopg.connect(dsn(), autocommit=True) as conn:
        conn.execute(sql)
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = 'agente'"
        ).fetchone()
        ident = psycopg.sql.SQL("ALTER ROLE agente WITH LOGIN PASSWORD {}").format(
            psycopg.sql.Literal(pwd)
        )
        create = psycopg.sql.SQL(
            "CREATE ROLE agente LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
        ).format(psycopg.sql.Literal(pwd))
        if exists:
            conn.execute(ident)
        else:
            conn.execute(create)
        conn.execute("REVOKE ALL ON SCHEMA public FROM agente")
        conn.execute("GRANT USAGE ON SCHEMA api TO agente")
        for stmt in (
            "GRANT EXECUTE ON FUNCTION api.catalogo() TO agente",
            "GRANT EXECUTE ON FUNCTION api.nominata(smallint, text, text, integer, text, bigint, integer, text, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.votacao(smallint, text, text, integer, boolean, smallint, text, bigint, integer, text, text, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.comparecimento(smallint, text, text, integer, boolean, smallint) TO agente",
            "GRANT EXECUTE ON FUNCTION api.eleitorado(smallint, text, integer, boolean) TO agente",
            "GRANT EXECUTE ON FUNCTION api.coligacao(smallint, text, text, integer, text, bigint, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.vagas(smallint, text, text, integer, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.bem(smallint, bigint, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.receita(smallint, bigint, text, text, text, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.despesa(smallint, bigint, text, text, text, integer) TO agente",
            "GRANT EXECUTE ON FUNCTION api.eleitos(smallint, text, text, integer, boolean, text, integer) TO agente",
        ):
            conn.execute(stmt)
        print("api+agente ok")
        load_env()
        from urllib.parse import urlsplit, urlunsplit

        base = os.environ.get("DATABASE_URL", "")
        parts = urlsplit(base)
        host = parts.hostname or ""
        port = parts.port or 5432
        dbname = (parts.path or "/iebrasil").lstrip("/")
        agente_url = f"postgresql://agente:{pwd}@{host}:{port}/{dbname}"
        envp = ROOT / ".env"
        text = envp.read_text(encoding="utf-8")
        if "AGENTE_DATABASE_URL=" not in text:
            with envp.open("a", encoding="utf-8") as f:
                f.write(f"\nAGENTE_DATABASE_URL={agente_url}\n")
        os.environ["AGENTE_DATABASE_URL"] = agente_url


if __name__ == "__main__":
    main()
