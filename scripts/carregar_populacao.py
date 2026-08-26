"""Carga contexto.populacao_mun a partir de br_mun_censo e br_mun_estimativas."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, dsn, year_dir


def parse_sidra(path: Path) -> list[tuple[int, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[int, int]] = []
    for row in data[1:]:
        cod = row.get("D1C")
        val = row.get("V")
        if not cod or val in (None, "", "...", "-"):
            continue
        try:
            out.append((int(cod), int(str(val).replace(".", ""))))
        except ValueError:
            continue
    return out


def load_file(url: str, ano: int, fonte: str, path: Path, cods_ok: set[int]) -> int:
    rows = [(ano, cod, qt, fonte) for cod, qt in parse_sidra(path) if cod in cods_ok]
    skipped = len(parse_sidra(path)) - len(rows)
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM contexto.populacao_mun WHERE ano = %s AND ds_fonte = %s",
                (ano, fonte),
            )
            with cur.copy(
                "COPY contexto.populacao_mun (ano, cod_ibge, qt_populacao, ds_fonte) FROM STDIN"
            ) as copy:
                for r in rows:
                    copy.write_row(r)
        conn.commit()
    print(fonte, ano, "ok", len(rows), "skip_fora_malha", skipped, flush=True)
    return len(rows)


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_populacao.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)
        cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    print("malha", len(cods), flush=True)

    tot = 0
    for ano in [2014, 2016, 2018, 2020, 2021, 2024, 2025]:
        d = year_dir("br_mun_estimativas", ano)
        p = d / "origem.json"
        if not p.exists():
            print("skip estimativa", ano)
            continue
        tot += load_file(url, ano, "estimativa", p, cods)
    for ano in [2010, 2022]:
        d = year_dir("br_mun_censo", ano)
        p = d / "origem.json"
        if not p.exists():
            print("skip censo", ano)
            continue
        tot += load_file(url, ano, "censo", p, cods)
    print("TOTAL linhas", tot, flush=True)


if __name__ == "__main__":
    main()
