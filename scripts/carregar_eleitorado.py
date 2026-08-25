"""Carga eleicao.eleitorado: soma zonas no município (não rateia)."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import as_int, as_text, dsn, iter_csv_rows, year_dir

UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)


def main() -> None:
    url = dsn()
    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE eleicao.eleitorado")
        conn.commit()
    for ano in (2014, 2016, 2018, 2020, 2022, 2024, 2026):
        d = year_dir("br_mun_eleitorado_perfil", ano)
        if not d.exists():
            print("skip eleitorado", ano)
            continue
        print("eleitorado", ano, flush=True)
        acc: dict[tuple, int] = defaultdict(int)
        ano_csv = None
        for row in iter_csv_rows(d):
            uf = (as_text(row.get("SG_UF")) or "").upper()
            if uf not in UFS_OK:
                continue
            mun = as_int(row.get("CD_MUNICIPIO"))
            qt = as_int(row.get("QT_ELEITORES")) or 0
            if mun is None:
                continue
            y = as_int(row.get("AA_ELEICAO")) or as_int(row.get("ANO_ELEICAO")) or ano
            ano_csv = y
            key = (
                y,
                uf,
                mun,
                as_text(row.get("DS_GENERO")) or "",
                as_text(row.get("DS_FAIXA_ETARIA")) or "",
                as_text(row.get("DS_GRAU_ESCOLARIDADE")) or "",
            )
            acc[key] += qt
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.eleitorado (
                      ano, sg_uf, cd_municipio_tse, ds_genero, ds_faixa_etaria,
                      ds_grau_escolaridade, qt_eleitores
                    ) FROM STDIN
                    """
                ) as copy:
                    for key, qt in acc.items():
                        copy.write_row((*key, qt))
            conn.commit()
        print("  linhas", len(acc), "ano_csv", ano_csv, flush=True)


if __name__ == "__main__":
    main()
