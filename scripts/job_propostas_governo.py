"""Job focado: baixar + carregar propostas de governo no acervo.

Uso no EasyPanel (comando do serviço ingest):
  python scripts/job_propostas_governo.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPTS = ROOT / "scripts"


def _run(name: str, *extra: str) -> None:
    print("\n>>>", name, *extra, flush=True)
    subprocess.check_call([PY, str(SCRIPTS / name), *extra], cwd=str(ROOT))


def main() -> None:
    anos = os.environ.get("INGEST_ANOS_PROPOSTAS", "2018,2022").replace(",", " ").split()
    code = 0
    try:
        _run("baixar_propostas_governo.py", *anos)
    except subprocess.CalledProcessError:
        code = 1
        print("AVISO: download propostas com falha", flush=True)
    try:
        _run("carregar_propostas_governo.py", *anos)
    except subprocess.CalledProcessError as e:
        code = max(code, e.returncode or 1)
        print("AVISO: carga propostas com falha", flush=True)
    print("JOB_PROPOSTAS_FIM", "code", code, anos, flush=True)
    secs = int(os.environ.get("JOB_SLEEP_AFTER", "3600"))
    print(f"sleep {secs}s (logs)", flush=True)
    import time

    time.sleep(secs)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
