"""Runner interno: pg_dump do banco iebrasil (não commitar credenciais)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backup_iebrasil.dump"
LOG = ROOT / "backup_iebrasil.log"
PID = ROOT / "backup_iebrasil.pid"
STATUS = ROOT / "backup_iebrasil.status"
PG_DUMP = Path(r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe")


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    load_env()
    url = os.environ.get("POSTGRES_ADMIN_URL") or os.environ.get("DATABASE_URL")
    if not url:
        STATUS.write_text("erro: sem POSTGRES_ADMIN_URL/DATABASE_URL\n", encoding="utf-8")
        return 1
    if not PG_DUMP.exists():
        STATUS.write_text(f"erro: pg_dump nao encontrado em {PG_DUMP}\n", encoding="utf-8")
        return 1

    p = urlparse(url)
    env = os.environ.copy()
    env["PGPASSWORD"] = p.password or ""
    host = p.hostname or "127.0.0.1"
    port = str(p.port or 5432)
    user = p.username or "iebrasil"
    db = (p.path or "/iebrasil").lstrip("/") or "iebrasil"

    if OUT.exists():
        OUT.unlink()

    LOG.write_text(f"iniciando pg_dump host={host} db={db}\n", encoding="utf-8")
    STATUS.write_text("rodando\n", encoding="utf-8")

    with LOG.open("a", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            [
                str(PG_DUMP),
                "-Fc",
                "-h",
                host,
                "-p",
                port,
                "-U",
                user,
                db,
                "-f",
                str(OUT),
            ],
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    PID.write_text(str(proc.pid), encoding="utf-8")
    code = proc.wait()
    if code == 0 and OUT.exists() and OUT.stat().st_size > 0:
        size = OUT.stat().st_size
        STATUS.write_text(f"ok bytes={size}\n", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as lf:
            lf.write(f"concluido exit=0 bytes={size}\n")
        return 0

    STATUS.write_text(f"erro exit={code}\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as lf:
        lf.write(f"falhou exit={code}\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
