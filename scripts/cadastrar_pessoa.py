"""Cadastra pessoa com token MCP individual vinculado a campanha."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp"))

from apura.cadastro import emitir_mcp_token  # noqa: E402
from tse_util import dsn, load_env  # noqa: E402


def cadastrar(nome: str, email: str, telefone: str, campanha_nome: str) -> str:
    load_env()
    with psycopg.connect(dsn(), autocommit=True) as conn:
        row = conn.execute(
            "SELECT id::text FROM ctl.campanha WHERE nome = %s AND ativo IS TRUE",
            (campanha_nome,),
        ).fetchone()
        if not row:
            raise SystemExit(f"Campanha '{campanha_nome}' não existe ou está inativa.")
        token = emitir_mcp_token(conn, nome, email, telefone, row[0])
    print(f"OK Token para {nome} ({campanha_nome}): {token}")
    return token


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Uso: python scripts/cadastrar_pessoa.py <nome> <email> <telefone> <campanha>")
        sys.exit(1)
    cadastrar(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
