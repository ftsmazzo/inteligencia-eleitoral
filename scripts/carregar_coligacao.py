"""Carga eleicao.coligacao a partir de br_cand_coligacao."""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path
from typing import Iterator

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, find_csvs, find_zip, year_dir

CARGOS_MUN = {11, 12, 13}
UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)


def iter_coligacao_rows(d: Path) -> Iterator[dict[str, str]]:
    """UF por arquivo; BRASIL só quando não há por-UF; _BR.csv traz Pres/Vice."""
    csvs = find_csvs(d)
    if not csvs:
        csvs = sorted(d.glob("*.csv"))
    if csvs:
        for csv_path in csvs:
            with csv_path.open("r", encoding="latin-1", newline="") as f:
                yield from csv.DictReader(f, delimiter=";")
        return
    zpath = find_zip(d)
    if not zpath:
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
    if cargo in CARGOS_MUN:
        return as_int(row.get("SG_UE"))
    return 0


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_coligacao_pk.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)

    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE eleicao.coligacao")
        conn.commit()

    total = 0
    for ano in (2014, 2016, 2018, 2020, 2022, 2024, 2026):
        d = year_dir("br_cand_coligacao", ano)
        tem_raw = d.exists() and (bool(list(d.glob("*.csv"))) or find_zip(d) is not None)
        if not tem_raw:
            print("skip coligacao", ano, "(sem raw)")
            continue
        print("coligacao", ano, flush=True)
        n = 0
        skipped = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.coligacao (
                      ano, cd_cargo, sg_uf, cd_municipio_tse, sq_coligacao,
                      nm_coligacao, ds_composicao, sg_partido
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    for row in iter_coligacao_rows(d):
                        tipo = as_int(row.get("CD_TIPO_ELEICAO"))
                        if tipo is not None and tipo != 2:
                            continue
                        uf = (as_text(row.get("SG_UF")) or "").upper()
                        if uf not in UFS_OK and uf != "BR":
                            continue
                        cargo = as_int(row.get("CD_CARGO"))
                        sq = as_int(row.get("SQ_COLIGACAO"))
                        pt = as_text(row.get("SG_PARTIDO"))
                        if cargo is None or sq is None or not pt:
                            skipped += 1
                            continue
                        mun = cd_municipio(row, cargo)
                        if mun is None:
                            skipped += 1
                            continue
                        sg_uf = uf if uf == "BR" else uf[:2]
                        key = (ano, cargo, sg_uf, mun, sq, pt)
                        if key in seen:
                            continue
                        seen.add(key)
                        copy.write_row(
                            (
                                ano,
                                cargo,
                                sg_uf,
                                mun,
                                sq,
                                as_text(row.get("NM_COLIGACAO")),
                                as_text(row.get("DS_COMPOSICAO_COLIGACAO")),
                                pt,
                            )
                        )
                        n += 1
            conn.commit()
        print("  linhas", n, "skip", skipped, flush=True)
        total += n
    print("coligacao total", total, flush=True)


if __name__ == "__main__":
    main()
