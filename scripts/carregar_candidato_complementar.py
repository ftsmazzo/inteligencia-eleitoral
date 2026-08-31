"""Carga eleicao.candidato_complementar a partir de br_cand_complementar."""
from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, iter_csv_rows, load_env, year_dir


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
    load_env()
    url = dsn()
    patch = (ROOT / "sql" / "patch_candidato_complementar_info.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)

    anos = [int(a) for a in sys.argv[1:]] or [2018, 2020, 2022, 2024, 2026]
    with psycopg.connect(url) as conn:
        for ano in anos:
            conn.execute("DELETE FROM eleicao.candidato_complementar WHERE ano = %s", (ano,))
        conn.commit()

    total = 0
    for ano in anos:
        d = year_dir("br_cand_complementar", ano)
        if not d.exists() or not list(d.glob("*.zip")):
            print("skip complementar", ano, flush=True)
            continue
        print("complementar", ano, flush=True)
        n = 0
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    """
                    COPY eleicao.candidato_complementar (
                      ano, sq_candidato, sg_uf,
                      ds_nacionalidade, nr_idade_data_posse, st_quilombola, ds_etnia_indigena,
                      vr_despesa_max_campanha, st_reeleicao, st_declarar_bens,
                      ds_detalhe_situacao_cand, ds_situacao_candidato_pleito,
                      ds_situacao_candidato_urna, st_candidato_inserido_urna,
                      st_prest_contas, st_substituido,
                      ds_situacao_julgamento, ds_situacao_cassacao, ds_situacao_diploma,
                      ds_genero_fefc, ds_cor_raca_fefc
                    ) FROM STDIN
                    """
                ) as copy:
                    seen: set[tuple] = set()
                    for row in iter_csv_rows(d):
                        sq = as_int(row.get("SQ_CANDIDATO"))
                        if sq is None:
                            continue
                        key = (ano, sq)
                        if key in seen:
                            continue
                        seen.add(key)
                        # UF: muitos CSVs são por UF; BR/BRASIL sem UF
                        uf = as_text(row.get("SG_UF"))
                        if uf and len(uf) > 2:
                            uf = uf[:2]
                        idade = as_int(row.get("NR_IDADE_DATA_POSSE"))
                        copy.write_row(
                            (
                                ano,
                                sq,
                                uf,
                                as_text(row.get("DS_NACIONALIDADE")),
                                idade if idade is not None and 0 < idade < 130 else None,
                                as_text(row.get("ST_QUILOMBOLA")),
                                as_text(row.get("DS_ETNIA_INDIGENA")),
                                as_money(row.get("VR_DESPESA_MAX_CAMPANHA")),
                                as_text(row.get("ST_REELEICAO")),
                                as_text(row.get("ST_DECLARAR_BENS")),
                                as_text(row.get("DS_DETALHE_SITUACAO_CAND")),
                                as_text(row.get("DS_SITUACAO_CANDIDATO_PLEITO")),
                                as_text(row.get("DS_SITUACAO_CANDIDATO_URNA")),
                                as_text(row.get("ST_CANDIDATO_INSERIDO_URNA")),
                                as_text(row.get("ST_PREST_CONTAS")),
                                as_text(row.get("ST_SUBSTITUIDO")),
                                as_text(row.get("DS_SITUACAO_JULGAMENTO")),
                                as_text(row.get("DS_SITUACAO_CASSACAO")),
                                as_text(row.get("DS_SITUACAO_DIPLOMA")),
                                as_text(row.get("DS_GENERO_FEFC")),
                                as_text(row.get("DS_COR_RACA_FEFC")),
                            )
                        )
                        n += 1
            conn.commit()
        print("  linhas", n, flush=True)
        total += n
    print("candidato_complementar total", total, flush=True)


if __name__ == "__main__":
    main()
