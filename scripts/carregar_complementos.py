"""Carrega módulos complementares (população, social, contas, parlamento) após núcleo ok.

Uso:
  python scripts/auditar_recorte.py          # gate — exit 0 obrigatório
  python scripts/carregar_complementos.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> None:
    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "auditar_recorte.py")],
        cwd=str(ROOT),
    )
    if gate.returncode != 0:
        raise SystemExit("Gate bloqueado: núcleo eleitoral falhou em auditar_recorte.py")

    steps = [
        [sys.executable, str(ROOT / "scripts" / "carregar_populacao.py")],
        [sys.executable, str(ROOT / "scripts" / "carregar_social.py")],
        [sys.executable, str(ROOT / "scripts" / "carregar_contas.py")],
        [sys.executable, str(ROOT / "scripts" / "carregar_parlamento.py")],
        [sys.executable, str(ROOT / "scripts" / "fechar_base.py")],
    ]
    for cmd in steps:
        script = Path(cmd[1]).name
        if not Path(cmd[1]).exists():
            print("skip", script)
            continue
        print(">>>", script)
        subprocess.check_call(cmd, cwd=str(ROOT))

    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "auditar_recorte.py"), "--write-docs"],
        cwd=str(ROOT),
    )
    print("COMPLEMENTOS_OK")


if __name__ == "__main__":
    main()
