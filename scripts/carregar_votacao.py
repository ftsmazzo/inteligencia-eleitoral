"""Carga eleicao.votacao (partição por ano). Sem arquivo BRASIL (duplicata das UFs)."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import as_int, as_text, dsn, iter_csv_rows, year_dir

UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)


def main() -> None:
    url = dsn()
    anos = [int(a) for a in sys.argv[1:]] or [2014, 2016, 2018, 2020, 2022, 2024]
    for ano in anos:
        d = year_dir("br_mun_votacao_nominal", ano)
        if not d.exists():
            print("skip votacao", ano)
            continue
        print("votacao", ano)
        with psycopg.connect(url) as conn:
            conn.execute(f"TRUNCATE eleicao.votacao_{ano}")
            conn.commit()
            n = 0
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.votacao (
                      ano, nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona,
                      sq_candidato, nr_candidato, nm_urna, sg_partido, qt_votos,
                      ds_sit_tot_turno
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    uf_lote = ""
                    for row in iter_csv_rows(d):
                        tipo = as_int(row.get("CD_TIPO_ELEICAO"))
                        if tipo is not None and tipo != 2:
                            continue
                        uf = (as_text(row.get("SG_UF")) or "").upper()
                        if uf not in UFS_OK:
                            continue
                        if uf != uf_lote:
                            seen = set()
                            uf_lote = uf
                        trans = (as_text(row.get("ST_VOTO_EM_TRANSITO")) or "N").upper()
                        if trans == "S":
                            continue
                        key = (
                            as_int(row.get("NR_TURNO")),
                            as_int(row.get("CD_CARGO")),
                            uf,
                            as_int(row.get("CD_MUNICIPIO")),
                            as_int(row.get("NR_ZONA")),
                            as_int(row.get("SQ_CANDIDATO")),
                        )
                        if None in key or key in seen:
                            continue
                        seen.add(key)
                        copy.write_row(
                            (
                                ano,
                                key[0],
                                key[1],
                                uf,
                                key[3],
                                key[4],
                                key[5],
                                as_int(row.get("NR_CANDIDATO")),
                                as_text(row.get("NM_URNA_CANDIDATO")),
                                as_text(row.get("SG_PARTIDO")),
                                as_int(row.get("QT_VOTOS_NOMINAIS")),
                                as_text(row.get("DS_SIT_TOT_TURNO")),
                            )
                        )
                        n += 1
                        if n % 2_000_000 == 0:
                            print("  linhas", n)
            conn.commit()
        print("  votacao", ano, "linhas", n)


if __name__ == "__main__":
    main()
