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
    _run("baixar_propostas_governo.py", *anos)
    _run("carregar_propostas_governo.py", *anos)
    print("JOB_PROPOSTAS_OK", anos, flush=True)


if __name__ == "__main__":
    main()
