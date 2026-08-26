"""Fecha pendências da base funcional: dicionário, parlamento complementar, catálogo."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tse_util import ROOT as _, dsn, load_env  # noqa: E402


def main() -> None:
    load_env()
    url = dsn()
    for name in ("patch_ref_dicionario.sql", "patch_parlamento.sql"):
        sql = (ROOT / "sql" / name).read_text(encoding="utf-8")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql)
        print("patch", name, "ok")

    # Só complementos parlamentares + de-para (rápido)
    from carregar_parlamento import (  # noqa: WPS433
        build_depara,
        load_orientacoes,
        load_temas,
    )

    with psycopg.connect(url) as conn:
        load_temas(conn)
        load_orientacoes(conn)
        build_depara(conn)
        conn.commit()

    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "gerar_catalogo_nucleo.py")])
    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "auditar_recorte.py"), "--write-docs"])
    print("FECHAR_BASE_OK")


if __name__ == "__main__":
    main()
