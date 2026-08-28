"""Job único: baixa complementos oficiais e carrega no Postgres.

Roda no serviço EasyPanel ingest-complementos (rede interna postgres:5432).

Uso local:
  DATABASE_URL=postgresql://... python scripts/job_complementos.py
  python scripts/job_complementos.py --skip-download   # só carga
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tse_util import dsn, load_env  # noqa: E402

PY = sys.executable
SCRIPTS = ROOT / "scripts"


def _nucleus_ok() -> bool:
    load_env()
    url = dsn()
    with psycopg.connect(url, connect_timeout=30) as conn:
        n = conn.execute("SELECT count(*) FROM eleicao.votacao WHERE ano = 2022").fetchone()[0]
    return int(n) > 1_000_000


def _run(name: str, *extra: str) -> None:
    script = SCRIPTS / name
    if not script.exists():
        print("skip", name)
        return
    print("\n>>>", name, flush=True)
    subprocess.check_call([PY, str(script), *extra], cwd=str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--anos-contas", default="2018,2022", help="Anos contas (CSV) — default leve")
    args = ap.parse_args()

    load_env()
    if not _nucleus_ok():
        raise SystemExit("Núcleo ausente no Postgres — abortando job complementos.")

    if not args.skip_download:
        for s in (
            "baixar_ibge_populacao.py",
            "baixar_parlamento.py",
            "baixar_contas.py",
        ):
            _run(s)

    _run("carregar_populacao.py")

    z_cad = ROOT / "data" / "raw" / "br_mun_cadunico" / "anomes=202607" / "origem.zip"
    z_bol = ROOT / "data" / "raw" / "br_mun_bolsa_familia" / "anomes=202608" / "origem.zip"
    if z_cad.exists() and z_bol.exists():
        _run("carregar_social.py")
    else:
        print("AVISO: social skip — zips MDS ausentes (promover inbox ou copiar raw)", flush=True)

    anos = [a.strip() for a in args.anos_contas.split(",") if a.strip()]
    _run("carregar_contas.py", *anos)
    _run("carregar_parlamento.py")
    _run("fechar_base.py")

    # patches analítico / grants (idempotente)
    for patch in ("patch_populacao.sql", "patch_social.sql", "patch_contas.sql", "patch_parlamento.sql", "patch_analitico.sql"):
        p = ROOT / "sql" / patch
        if p.exists():
            with psycopg.connect(dsn(), autocommit=True) as conn:
                conn.execute(p.read_text(encoding="utf-8"))

    with psycopg.connect(dsn(), connect_timeout=30) as conn:
        stats = {
            "populacao": conn.execute("SELECT count(*) FROM contexto.populacao_mun").fetchone()[0],
            "cadunico": conn.execute("SELECT count(*) FROM contexto.cadunico_mun").fetchone()[0],
            "bolsa": conn.execute("SELECT count(*) FROM contexto.bolsa_familia_mun").fetchone()[0],
            "receita": conn.execute("SELECT count(*) FROM eleicao.receita").fetchone()[0],
            "deputados": conn.execute("SELECT count(*) FROM parlamentar.deputado").fetchone()[0],
            "proposicoes": conn.execute("SELECT count(*) FROM parlamentar.proposicao").fetchone()[0],
        }
    print("\nJOB_COMPLEMENTOS_OK", stats, flush=True)
    secs = int(os.environ.get("JOB_SLEEP_AFTER", "3600"))
    print(f"sleep {secs}s (logs)", flush=True)
    import time
    time.sleep(secs)


if __name__ == "__main__":
    main()
