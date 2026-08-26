"""Carga contexto.cadunico_mun e contexto.bolsa_familia_mun."""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, RAW, dsn


def as_int(v: str | None) -> int | None:
    if v is None:
        return None
    s = v.strip()
    if not s or s.upper() in {"NULL", "NONE", "-", "..."}:
        return None
    try:
        return int(Decimal(s.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def as_num(v: str | None) -> Decimal | None:
    if v is None:
        return None
    s = v.strip()
    if not s or s.upper() in {"NULL", "NONE", "-", "..."}:
        return None
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


def map6(cods7: dict[int, int], codigo6: int) -> int | None:
    return cods7.get(codigo6)


def load_cadunico(url: str, zpath: Path, cods7: dict[int, int]) -> int:
    n = 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE contexto.cadunico_mun")
            with cur.copy(
                """
                COPY contexto.cadunico_mun (
                  anomes, cod_ibge, qt_familias, qt_familias_ate_meio_sm, qt_familias_acima_meio_sm,
                  qt_familias_pobreza_pbf, qt_familias_baixa_renda, qt_familias_extrema_pobreza,
                  qt_pessoas_ate_meio_sm, qt_pessoas_acima_meio_sm, taxa_atualizacao_ate_meio_sm
                ) FROM STDIN
                """
            ) as copy:
                with zipfile.ZipFile(zpath) as zf:
                    for name in sorted(zf.namelist()):
                        if not name.lower().endswith(".csv"):
                            continue
                        with zf.open(name) as raw:
                            reader = csv.DictReader(
                                io.TextIOWrapper(raw, encoding="utf-8", newline="")
                            )
                            for row in reader:
                                c6 = as_int(row.get("codigo_ibge"))
                                if c6 is None:
                                    continue
                                c7 = map6(cods7, c6)
                                if c7 is None:
                                    continue
                                copy.write_row(
                                    (
                                        as_int(row.get("anomes_s")),
                                        c7,
                                        as_int(row.get("cadun_qtd_familias_cadastradas_i")),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_familias_cadastradas_rfpc_ate_meio_sm_i"
                                            )
                                        ),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_familias_cadastradas_rfpc_acima_meio_sm_i"
                                            )
                                        ),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_familias_cadastradas_pobreza_pbf_i"
                                            )
                                        ),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_familias_cadastradas_baixa_renda_i"
                                            )
                                        ),
                                        as_int(
                                            row.get("cadun_qtde_fam_sit_extrema_pobreza_s")
                                        ),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_pessoas_cadastradas_rfpc_ate_meio_sm_i"
                                            )
                                        ),
                                        as_int(
                                            row.get(
                                                "cadun_qtd_pessoas_cadastradas_rfpc_acima_meio_sm_i"
                                            )
                                        ),
                                        as_num(
                                            row.get(
                                                "cadun_taxa_atualizacao_cadastral_rfpc_ate_meio_sm_d"
                                            )
                                        ),
                                    )
                                )
                                n += 1
        conn.commit()
    return n


def load_bolsa(url: str, zpath: Path, cods7: dict[int, int]) -> int:
    n = 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE contexto.bolsa_familia_mun")
            with cur.copy(
                """
                COPY contexto.bolsa_familia_mun (
                  anomes, cod_ibge, qt_familias, qt_pessoas, vr_repassado,
                  vr_medio_beneficio, pct_familias_rf_mulher
                ) FROM STDIN
                """
            ) as copy:
                with zipfile.ZipFile(zpath) as zf:
                    for name in sorted(zf.namelist()):
                        if not name.lower().endswith(".csv"):
                            continue
                        with zf.open(name) as raw:
                            reader = csv.DictReader(
                                io.TextIOWrapper(raw, encoding="utf-8", newline="")
                            )
                            for row in reader:
                                c6 = as_int(row.get("codigo_ibge"))
                                if c6 is None:
                                    continue
                                c7 = map6(cods7, c6)
                                if c7 is None:
                                    continue
                                copy.write_row(
                                    (
                                        as_int(row.get("anomes_s")),
                                        c7,
                                        as_int(
                                            row.get(
                                                "qtd_familias_beneficiarias_bolsa_familia_i"
                                            )
                                        ),
                                        as_int(
                                            row.get(
                                                "qtd_pessoas_beneficiarias_bolsa_familia_i"
                                            )
                                        ),
                                        as_num(row.get("valor_repassado_bolsa_familia_f")),
                                        as_num(row.get("pbf_vlr_medio_benef_f")),
                                        as_num(
                                            row.get("pbf_perc_familias_benef_rf_mulher_d")
                                        ),
                                    )
                                )
                                n += 1
        conn.commit()
    return n


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_social.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)
        cods7 = {
            r[0] // 10: r[0]
            for r in conn.execute("SELECT cod_ibge FROM ref.municipio")
        }
    print("malha6", len(cods7), flush=True)

    z_cad = RAW / "br_mun_cadunico" / "anomes=202607" / "origem.zip"
    z_bol = RAW / "br_mun_bolsa_familia" / "anomes=202608" / "origem.zip"
    if not z_cad.exists() or not z_bol.exists():
        raise SystemExit("rode scripts/promover_social_inbox.py antes")

    n1 = load_cadunico(url, z_cad, cods7)
    print("cadunico", n1, flush=True)
    n2 = load_bolsa(url, z_bol, cods7)
    print("bolsa", n2, flush=True)
    print("TOTAL", n1 + n2, flush=True)


if __name__ == "__main__":
    main()
