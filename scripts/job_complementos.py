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


def _downloads_ready() -> bool:
    probe = ROOT / "data" / "raw" / "br_mun_estimativas" / "ano=2024" / "origem.json"
    return probe.exists()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--anos-contas", default="2018,2022", help="Anos contas (CSV) — default leve")
    args = ap.parse_args()

    load_env()
    if not _nucleus_ok():
        raise SystemExit("Núcleo ausente no Postgres — abortando job complementos.")

    skip_dl = args.skip_download or os.environ.get("INGEST_SKIP_DOWNLOAD", "").strip() in ("1", "true", "yes")
    anos_prop = os.environ.get("INGEST_ANOS_PROPOSTAS", "2018,2022").replace(",", " ").split()
    if not skip_dl and _downloads_ready():
        print("AVISO: downloads já em data/raw — pulando baixar_ibge/parlamento/contas", flush=True)
        skip_dl = True
    if not skip_dl:
        anos_dl = args.anos_contas.replace(",", " ").split()
        for s in (
            "baixar_ibge_populacao.py",
            "baixar_parlamento.py",
        ):
            _run(s)
        _run("baixar_contas.py", *anos_dl)

    # propostas: baixa se faltar ZIP (independente do skip dos outros)
    faltam_prop = [
        a
        for a in anos_prop
        if not (ROOT / "data" / "raw" / "acervo_plano_governo" / f"ano={a}" / "origem.zip").exists()
    ]
    if faltam_prop and not args.skip_download:
        _run("baixar_propostas_governo.py", *faltam_prop)
    elif not faltam_prop:
        print("JA TEM propostas", ",".join(anos_prop), flush=True)

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

    prop_ok = any(
        (ROOT / "data" / "raw" / "acervo_plano_governo" / f"ano={a}" / "origem.zip").exists()
        for a in anos_prop
    )
    if prop_ok:
        try:
            _run("carregar_propostas_governo.py", *anos_prop)
        except subprocess.CalledProcessError as e:
            print("AVISO: carga propostas falhou —", e, flush=True)
    else:
        print("AVISO: propostas skip — rode baixar_propostas_governo.py", flush=True)

    # patches analítico / grants (idempotente) — sem fechar_base (exige docs/ no repo)
    for patch in (
        "patch_ref_dicionario.sql",
        "patch_populacao.sql",
        "patch_social.sql",
        "patch_contas.sql",
        "patch_parlamento.sql",
        "patch_analitico.sql",
    ):
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
