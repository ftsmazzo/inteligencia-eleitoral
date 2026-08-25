"""Carga eleicao.detalhe_munzona."""
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
    for ano in (2014, 2016, 2018, 2020, 2022, 2024):
        d = year_dir("br_mun_detalhe_apuracao", ano)
        if not d.exists():
            print("skip detalhe", ano)
            continue
        print("detalhe", ano)
        with psycopg.connect(url) as conn:
            conn.execute(f"TRUNCATE eleicao.detalhe_{ano}")
            conn.commit()
            n = 0
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.detalhe_munzona (
                      ano, nr_turno, cd_cargo, sg_uf, cd_municipio_tse, nr_zona,
                      qt_aptos, qt_comparecimento, qt_abstencoes, qt_votos_brancos,
                      qt_votos_nulos, qt_votos_nominais, qt_votos_legenda
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
                        )
                        if None in key or key in seen:
                            continue
                        seen.add(key)
                        nulos = as_int(row.get("QT_TOTAL_VOTOS_NULOS"))
                        if nulos is None:
                            nulos = as_int(row.get("QT_VOTOS_NULOS"))
                        nominais = as_int(row.get("QT_VOTOS_NOMINAIS_VALIDOS"))
                        if nominais is None:
                            nominais = as_int(row.get("QT_VOTOS_NOMINAIS"))
                        legenda = as_int(row.get("QT_VOTOS_LEG_VALIDOS"))
                        if legenda is None:
                            legenda = as_int(row.get("QT_VOTOS_LEGENDA"))
                        copy.write_row(
                            (
                                ano,
                                key[0],
                                key[1],
                                uf,
                                key[3],
                                key[4],
                                as_int(row.get("QT_APTOS")),
                                as_int(row.get("QT_COMPARECIMENTO")),
                                as_int(row.get("QT_ABSTENCOES")),
                                as_int(row.get("QT_VOTOS_BRANCOS")),
                                nulos,
                                nominais,
                                legenda,
                            )
                        )
                        n += 1
            conn.commit()
        print("  linhas", n)


if __name__ == "__main__":
    main()
