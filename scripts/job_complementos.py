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
    ap.add_argument(
        "--anos-contas",
        default=os.environ.get("INGEST_ANOS_CONTAS", "2014,2016,2018,2020,2022,2024"),
        help="Anos contas — default todos no banco (TRUNCATE exige lista completa)",
    )
    args = ap.parse_args()

    load_env()
    if not _nucleus_ok():
        raise SystemExit("Núcleo ausente no Postgres — abortando job complementos.")

    skip_dl = args.skip_download or os.environ.get("INGEST_SKIP_DOWNLOAD", "").strip() in ("1", "true", "yes")
    skip_prop = os.environ.get("INGEST_SKIP_PROPOSTAS", "").strip() in ("1", "true", "yes")
    skip_contas = os.environ.get("INGEST_SKIP_CONTAS", "").strip() in ("1", "true", "yes")
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

    # propostas: baixa se faltar ZIP (respeita skip_dl e INGEST_SKIP_PROPOSTAS)
    faltam_prop = [
        a
        for a in anos_prop
        if not (ROOT / "data" / "raw" / "acervo_plano_governo" / f"ano={a}" / "origem.zip").exists()
    ]
    if faltam_prop and not skip_dl and not skip_prop:
        try:
            _run("baixar_propostas_governo.py", *faltam_prop)
        except subprocess.CalledProcessError as e:
            print("AVISO: download propostas falhou (ex. CDN 403) —", e, flush=True)
    elif skip_prop:
        print("SKIP propostas (INGEST_SKIP_PROPOSTAS)", flush=True)
    elif not faltam_prop:
        print("JA TEM propostas", ",".join(anos_prop), flush=True)
    else:
        print("AVISO: propostas ZIP ausente e download pulado", flush=True)

    _run("carregar_populacao.py")

    z_cad = ROOT / "data" / "raw" / "br_mun_cadunico" / "anomes=202607" / "origem.zip"
    z_bol = ROOT / "data" / "raw" / "br_mun_bolsa_familia" / "anomes=202608" / "origem.zip"
    if z_cad.exists() and z_bol.exists():
        _run("carregar_social.py")
    else:
        print("AVISO: social skip — zips MDS ausentes (promover inbox ou copiar raw)", flush=True)

    anos = [a.strip() for a in args.anos_contas.split(",") if a.strip()]
    if skip_contas:
        print("SKIP carregar_contas (INGEST_SKIP_CONTAS) — evita TRUNCATE", flush=True)
    else:
        _run("carregar_contas.py", *anos)
    _run("carregar_parlamento.py")

    prop_ok = any(
        (ROOT / "data" / "raw" / "acervo_plano_governo" / f"ano={a}" / "origem.zip").exists()
        for a in anos_prop
    )
    if prop_ok and not skip_prop:
        try:
            _run("carregar_propostas_governo.py", *anos_prop)
        except subprocess.CalledProcessError as e:
            print("AVISO: carga propostas falhou —", e, flush=True)
    else:
        print("AVISO: propostas skip — ZIP ausente ou INGEST_SKIP_PROPOSTAS", flush=True)

    # patches analítico / grants (idempotente) — sem fechar_base (exige docs/ no repo)
    def _apply_sql_file(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
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
        with psycopg.connect(dsn(), autocommit=True) as conn:
            for stmt in stmts:
                try:
                    conn.execute(stmt)
                except Exception as e:
                    print("AVISO patch", path.name, e, flush=True)

    for patch in (
        "patch_ref_dicionario.sql",
        "patch_populacao.sql",
        "patch_social.sql",
        "patch_contas.sql",
        "patch_parlamento.sql",
        "patch_analitico.sql",
        "patch_contas_resumo.sql",
        "patch_rede_complementar_api.sql",
    ):
        p = ROOT / "sql" / patch
        if p.exists():
            _apply_sql_file(p)

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
