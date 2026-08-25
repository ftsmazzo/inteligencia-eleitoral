"""Carga eleicao.candidatura a partir de br_cand_nominata."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import as_int, as_text, dsn, iter_csv_rows, year_dir

CARGOS_MUN = {11, 12, 13}


def main() -> None:
    url = dsn()
    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE eleicao.candidatura")
        conn.commit()

    total = 0
    for ano in (2014, 2016, 2018, 2020, 2022, 2024, 2026):
        d = year_dir("br_cand_nominata", ano)
        if not d.exists():
            print("skip nominata", ano)
            continue
        print("nominata", ano)
        n = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.candidatura (
                      ano, cd_cargo, sg_uf, cd_municipio_tse, sq_candidato,
                      nr_candidato, nm_urna, nm_candidato, sg_partido,
                      nm_coligacao, ds_situacao
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[int] = set()
                    for row in iter_csv_rows(d):
                        tipo = as_int(row.get("CD_TIPO_ELEICAO"))
                        if tipo is not None and tipo != 2:
                            continue
                        sq = as_int(row.get("SQ_CANDIDATO"))
                        if sq is None or sq in seen:
                            continue
                        seen.add(sq)
                        cargo = as_int(row.get("CD_CARGO"))
                        uf = as_text(row.get("SG_UF"))
                        if cargo is None or not uf:
                            continue
                        ue = as_int(row.get("SG_UE"))
                        mun = ue if cargo in CARGOS_MUN else None
                        copy.write_row(
                            (
                                ano,
                                cargo,
                                uf[:2],
                                mun,
                                sq,
                                as_int(row.get("NR_CANDIDATO")),
                                as_text(row.get("NM_URNA_CANDIDATO")),
                                as_text(row.get("NM_CANDIDATO")),
                                as_text(row.get("SG_PARTIDO")),
                                as_text(row.get("NM_COLIGACAO")),
                                as_text(row.get("DS_SITUACAO_CANDIDATURA")),
                            )
                        )
                        n += 1
            conn.commit()
        print("  linhas", n)
        total += n
    print("nominata total", total)


if __name__ == "__main__":
    main()
