"""Carga eleicao.bem a partir de br_cand_bens."""
from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, iter_csv_rows, year_dir


def as_money(v: str | None) -> Decimal | None:
    if v is None:
        return None
    s = v.strip()
    if not s or s.upper() in {"#NULO#", "#NE#", "#NI#"}:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s and s.count(",") == 1 else s
    try:
        return Decimal(s)
    except InvalidOperation:
        try:
            return Decimal(v.replace(",", "."))
        except InvalidOperation:
            return None


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_candidato_complementar.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)

    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE eleicao.bem")
        conn.commit()

    total = 0
    for ano in (2014, 2016, 2018, 2020, 2022, 2024, 2026):
        d = year_dir("br_cand_bens", ano)
        if not d.exists() or not list(d.glob("*.zip")):
            print("skip bens", ano)
            continue
        print("bens", ano, flush=True)
        n = 0
        skipped = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.bem (
                      ano, sq_candidato, nr_ordem, cd_tipo_bem, ds_tipo_bem, ds_bem, vr_bem
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    for row in iter_csv_rows(d):
                        tipo = as_int(row.get("CD_TIPO_ELEICAO"))
                        if tipo is not None and tipo not in (1, 2):
                            continue
                        sq = as_int(row.get("SQ_CANDIDATO"))
                        ordem = (
                            as_int(row.get("NR_ORDEM_BEM_CANDIDATO"))
                            or as_int(row.get("NR_ORDEM_CANDIDATO"))
                            or as_int(row.get("NR_ORDEM"))
                        )
                        if sq is None or ordem is None:
                            skipped += 1
                            continue
                        key = (ano, sq, ordem)
                        if key in seen:
                            continue
                        seen.add(key)
                        copy.write_row(
                            (
                                ano,
                                sq,
                                ordem,
                                as_int(row.get("CD_TIPO_BEM_CANDIDATO")),
                                as_text(row.get("DS_TIPO_BEM_CANDIDATO")),
                                as_text(row.get("DS_BEM_CANDIDATO")),
                                as_money(row.get("VR_BEM_CANDIDATO")),
                            )
                        )
                        n += 1
            conn.commit()
        print("  linhas", n, "skip", skipped, flush=True)
        total += n
    print("bens total", total, flush=True)


if __name__ == "__main__":
    main()
