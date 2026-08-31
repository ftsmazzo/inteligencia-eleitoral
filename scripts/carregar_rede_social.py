"""Carga eleicao.rede_social a partir de br_cand_rede_social."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, iter_csv_rows, load_env, year_dir


def main() -> None:
    load_env()
    url = dsn()
    patch = (ROOT / "sql" / "patch_candidato_complementar.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)

    anos = [int(a) for a in sys.argv[1:]] or [2020, 2022, 2024, 2026]
    with psycopg.connect(url) as conn:
        for ano in anos:
            conn.execute("DELETE FROM eleicao.rede_social WHERE ano = %s", (ano,))
        conn.commit()

    total = 0
    for ano in anos:
        d = year_dir("br_cand_rede_social", ano)
        if not d.exists() or not list(d.glob("*.zip")):
            print("skip rede", ano, flush=True)
            continue
        print("rede", ano, flush=True)
        n = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.rede_social (ano, sq_candidato, nr_ordem, ds_url, sg_uf)
                    FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    for row in iter_csv_rows(d):
                        sq = as_int(row.get("SQ_CANDIDATO"))
                        url_s = as_text(row.get("DS_URL"))
                        if sq is None or not url_s:
                            continue
                        ordem = as_int(row.get("NR_ORDEM_REDE_SOCIAL")) or 1
                        uf = as_text(row.get("SG_UF"))
                        if uf and len(uf) > 2:
                            uf = uf[:2]
                        key = (ano, sq, ordem, url_s)
                        if key in seen:
                            continue
                        seen.add(key)
                        copy.write_row((ano, sq, ordem, url_s, uf))
                        n += 1
            conn.commit()
        print("  linhas", n, flush=True)
        total += n
    print("rede_social total", total, flush=True)


if __name__ == "__main__":
    main()
