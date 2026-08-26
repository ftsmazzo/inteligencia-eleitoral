"""Carga eleicao.vagas a partir de br_cand_vagas (consulta_vagas)."""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path
from typing import Iterator

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, find_zip, year_dir

CARGOS_MUN = {11, 12, 13}
UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)


def iter_vagas_rows(d: Path) -> Iterator[dict[str, str]]:
    zpath = find_zip(d)
    if not zpath:
        for csv_path in sorted(d.glob("*.csv")):
            with csv_path.open("r", encoding="latin-1", newline="") as f:
                yield from csv.DictReader(f, delimiter=";")
        return
    with zipfile.ZipFile(zpath) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        per_uf = [
            n
            for n in members
            if "BRASIL" not in n.replace("\\", "/").split("/")[-1].upper()
            and not n.replace("\\", "/").split("/")[-1].upper().endswith("_BR.CSV")
        ]
        br_pres = [
            n
            for n in members
            if n.replace("\\", "/").split("/")[-1].upper().endswith("_BR.CSV")
        ]
        to_read = (per_uf + br_pres) if per_uf else members
        to_read.sort()
        for name in to_read:
            with zf.open(name) as raw:
                wrapper = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                yield from csv.DictReader(wrapper, delimiter=";")


def cd_municipio(row: dict, cargo: int) -> int | None:
    ue = as_text(row.get("SG_UE"))
    if cargo in CARGOS_MUN:
        return as_int(ue)
    return 0


def qt_vaga(row: dict) -> int | None:
    return as_int(row.get("QT_VAGA")) or as_int(row.get("QT_VAGAS"))


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_vagas.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)

    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE eleicao.vagas")
        conn.commit()

    total = 0
    for ano in (2014, 2016, 2018, 2020, 2022, 2024, 2026):
        d = year_dir("br_cand_vagas", ano)
        z = find_zip(d) if d.exists() else None
        if not d.exists() or (not z and not list(d.glob("*.csv"))):
            print("skip vagas", ano, "(sem raw)")
            continue
        print("vagas", ano, flush=True)
        n = 0
        skipped = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.vagas (
                      ano, cd_cargo, sg_uf, cd_municipio_tse, qt_vagas
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    for row in iter_vagas_rows(d):
                        uf = (as_text(row.get("SG_UF")) or "").upper()
                        if uf not in UFS_OK and uf != "BR":
                            continue
                        cargo = as_int(row.get("CD_CARGO"))
                        qtv = qt_vaga(row)
                        if cargo is None or qtv is None:
                            skipped += 1
                            continue
                        mun = cd_municipio(row, cargo)
                        if mun is None:
                            skipped += 1
                            continue
                        sg_uf = uf if uf == "BR" else uf[:2]
                        key = (ano, cargo, sg_uf, mun)
                        if key in seen:
                            continue
                        seen.add(key)
                        copy.write_row((ano, cargo, sg_uf, mun, qtv))
                        n += 1
            conn.commit()
        print("  linhas", n, "skip", skipped, flush=True)
        total += n
    print("vagas total", total, flush=True)


if __name__ == "__main__":
    main()
