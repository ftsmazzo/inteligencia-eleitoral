"""De-para CD município TSE ↔ IBGE 7 dígitos. Atualiza ref.municipio.cd_municipio_tse."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, iter_csv_rows, norm_nome, year_dir

QA = ROOT / "data" / "qa" / "br_depara_tse_ibge"
UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)

# (UF, nome TSE já normalizado) -> nome IBGE normalizado
ALIAS: dict[tuple[str, str], str] = {
    ("SP", "EMBU"): "EMBU DAS ARTES",
    ("CE", "ITAPAGE"): "ITAPAJE",
    ("RO", "ESPIGAO DO OESTE"): "ESPIGAO D OESTE",
    ("RO", "ALVORADA DO OESTE"): "ALVORADA D OESTE",
    ("RR", "SAO LUIZ"): "SAO LUIZ DO ANAUA",
    ("PA", "ELDORADO DOS CARAJAS"): "ELDORADO DO CARAJAS",
    ("PA", "SANTA ISABEL DO PARA"): "SANTA IZABEL DO PARA",
    ("RN", "BOA SAUDE"): "JANUARIO CICCO",
    ("SE", "AMPARO DE SAO FRANCISCO"): "AMPARO DO SAO FRANCISCO",
    ("BA", "CAMACA"): "CAMACAN",
    ("MG", "BARAO DE MONTE ALTO"): "BARAO DO MONTE ALTO",
    ("MG", "DONA EUSEBIA"): "DONA EUZEBIA",
    ("MG", "SAO THOME DAS LETRAS"): "SAO TOME DAS LETRAS",
    ("SP", "SAO LUIS DO PARAITINGA"): "SAO LUIZ DO PARAITINGA",
    ("MT", "SANTO ANTONIO DO LEVERGER"): "SANTO ANTONIO DE LEVERGER",
}


def coletar_tse() -> dict[int, tuple[str, str]]:
    """cd_tse -> (uf, nome mais frequente)."""
    freq: dict[int, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for ano in (2024, 2022, 2020, 2018, 2016, 2014):
        d = year_dir("br_mun_votacao_nominal", ano)
        if not d.exists():
            print("skip votacao", ano)
            continue
        print("scan votacao", ano)
        n = 0
        for row in iter_csv_rows(d):
            n += 1
            uf = (as_text(row.get("SG_UF")) or "").upper()
            if uf not in UFS_OK:
                continue
            cd = as_int(row.get("CD_MUNICIPIO"))
            nm = as_text(row.get("NM_MUNICIPIO"))
            if cd is None or not nm:
                continue
            freq[cd][(uf, nm)] += 1
            if n % 2_000_000 == 0:
                print(" ", ano, "linhas", n, "tse unicos", len(freq), flush=True)
        print(" ", ano, "fim linhas", n, "tse unicos", len(freq), flush=True)
        if len(freq) >= 5571:
            break
    chosen: dict[int, tuple[str, str]] = {}
    for cd, names in freq.items():
        (uf, nm), _ = max(names.items(), key=lambda kv: kv[1])
        chosen[cd] = (uf, nm)
    return chosen


def main() -> None:
    tse = coletar_tse()
    with psycopg.connect(dsn()) as conn:
        mun = conn.execute(
            "SELECT cod_ibge, sg_uf, nome FROM ref.municipio"
        ).fetchall()
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for cod, uf, nome in mun:
        by_key[(uf, norm_nome(nome))].append(int(cod))

    matched: list[tuple[int, int, str, str]] = []  # tse, ibge, uf, nome_tse
    unmatched: list[dict] = []
    used_ibge: dict[int, int] = {}

    for cd_tse, (uf, nm) in sorted(tse.items()):
        key_nm = ALIAS.get((uf, norm_nome(nm)), norm_nome(nm))
        cands = by_key.get((uf, key_nm), [])
        if len(cands) != 1:
            unmatched.append(
                {"cd_tse": cd_tse, "sg_uf": uf, "nm_tse": nm, "norm": key_nm, "ibge": cands}
            )
            continue
        ibge = cands[0]
        if ibge in used_ibge and used_ibge[ibge] != cd_tse:
            unmatched.append(
                {
                    "cd_tse": cd_tse,
                    "sg_uf": uf,
                    "nm_tse": nm,
                    "conflito_ibge": ibge,
                    "outro_tse": used_ibge[ibge],
                }
            )
            continue
        used_ibge[ibge] = cd_tse
        matched.append((cd_tse, ibge, uf, nm))

    with psycopg.connect(dsn()) as conn:
        conn.execute("UPDATE ref.municipio SET cd_municipio_tse = NULL")
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE ref.municipio SET cd_municipio_tse = %s WHERE cod_ibge = %s",
                [(tse_cd, ibge) for tse_cd, ibge, _, _ in matched],
            )
        conn.commit()
        cob = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE cd_municipio_tse IS NOT NULL), COUNT(*) FROM ref.municipio"
        ).fetchone()

    QA.mkdir(parents=True, exist_ok=True)
    ancora = {
        "tse_codigos_vistos": len(tse),
        "pareados": len(matched),
        "municipios_com_tse": cob[0],
        "municipios_malha": cob[1],
        "nao_pareados": unmatched[:200],
        "nao_pareados_n": len(unmatched),
    }
    (QA / "ancora.json").write_text(
        json.dumps(ancora, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("pareados", len(matched), "malha com tse", cob, "nao_pareados", len(unmatched))
    for u in unmatched[:15]:
        print("  GAP", u)


if __name__ == "__main__":
    main()
