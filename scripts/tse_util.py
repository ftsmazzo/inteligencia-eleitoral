"""Leitura de zips/CSV do TSE em data/raw. Encoding latin-1, ;."""
from __future__ import annotations

import csv
import io
import os
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

NULO = {"", "#NULO#", "#NE#", "#NI#", "#NULO", "-1", "NULL"}


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def dsn() -> str:
    load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL")
    return url


def year_dir(id_base: str, ano: int | str) -> Path:
    return RAW / id_base / f"ano={ano}"


def find_zip(d: Path) -> Path | None:
    named = d / "origem.zip"
    if named.exists():
        return named
    zips = sorted(d.glob("*.zip"))
    return zips[0] if zips else None


def find_csvs(d: Path) -> list[Path]:
    return sorted(p for p in d.glob("*.csv") if "BRASIL" not in p.name.upper())


def skip_member(name: str) -> bool:
    u = name.replace("\\", "/").split("/")[-1].upper()
    if not u.endswith(".CSV"):
        return True
    # arquivo nacional agregado — evita duplicar UFs
    if u.endswith("_BRASIL.CSV") or "_BRASIL_" in u:
        return True
    return False


def iter_csv_rows(d: Path) -> Iterator[dict[str, str]]:
    zpath = find_zip(d)
    if zpath:
        with zipfile.ZipFile(zpath) as zf:
            members = [n for n in zf.namelist() if not skip_member(n)]
            members.sort()
            for name in members:
                with zf.open(name) as raw:
                    wrapper = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                    yield from csv.DictReader(wrapper, delimiter=";")
        return
    for csv_path in find_csvs(d):
        with csv_path.open("r", encoding="latin-1", newline="") as f:
            yield from csv.DictReader(f, delimiter=";")


def as_int(v: str | None) -> int | None:
    if v is None:
        return None
    s = v.strip()
    if s.upper() in NULO or s in NULO:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def as_text(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if s.upper() in NULO:
        return None
    return s or None


def norm_nome(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())
