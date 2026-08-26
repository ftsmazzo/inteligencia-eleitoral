"""Carga eleicao.receita e eleicao.despesa a partir de br_cand_contas."""
from __future__ import annotations

import csv
import io
import re
import sys
import unicodedata
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, as_int, as_text, dsn, find_zip, year_dir

UFS_OK = set(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO BR".split()
)


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def row_get(row: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def as_money(v: str | None) -> Decimal | None:
    if v is None:
        return None
    s = v.strip()
    if not s or s.upper() in {"#NULO#", "#NE#", "#NI#", "NULL"}:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def as_date(v: str | None):
    if not v:
        return None
    s = v.strip()
    if not s or s.upper() in {"#NULO#", "#NE#"}:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19] if len(s) > 10 and " " in s else s[:10], fmt).date()
        except ValueError:
            continue
    # try first 10 chars dd/mm/yyyy
    try:
        return datetime.strptime(s[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def normalize_row(raw: dict[str, str]) -> dict[str, str]:
    return {norm_key(k): (v if v is not None else "") for k, v in raw.items()}


def skip_member(name: str, kind: str) -> bool:
    u = name.replace("\\", "/").split("/")[-1].upper()
    if "BRASIL" in u:
        return True
    if kind == "receita":
        return "RECEITA" not in u or "CANDIDATO" not in u
    # despesa: contratadas (2018+) ou despesas_candidatos (2014/2016); evita pagas duplicadas se existir
    if "DESPESA" not in u or "CANDIDATO" not in u:
        return True
    if "PAGA" in u:
        return True
    return False


def iter_members(zpath: Path, kind: str) -> Iterator[tuple[str, Any]]:
    with zipfile.ZipFile(zpath) as zf:
        members = [n for n in zf.namelist() if not skip_member(n, kind)]
        members = [n for n in members if n.lower().endswith((".csv", ".txt"))]
        members.sort()
        for name in members:
            with zf.open(name) as raw:
                wrapper = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                yield name, csv.DictReader(wrapper, delimiter=";")


def map_receita(ano: int, row: dict[str, str]) -> tuple | None:
    r = normalize_row(row)
    sq = as_int(row_get(r, "sq_candidato", "sequencial_candidato"))
    uf = (as_text(row_get(r, "sg_uf", "uf")) or "").upper()[:2] or None
    if uf and uf not in UFS_OK:
        return None
    vr = as_money(row_get(r, "vr_receita", "valor_receita"))
    if vr is None:
        return None
    return (
        ano,
        sq,
        uf,
        as_text(row_get(r, "sg_partido", "sigla_partido", "sigla__partido")),
        as_int(row_get(r, "nr_candidato", "numero_candidato")),
        as_text(row_get(r, "ds_cargo", "cargo")),
        as_text(row_get(r, "nm_candidato", "nome_candidato")),
        as_int(row_get(r, "sq_receita")),
        as_date(row_get(r, "dt_receita", "data_da_receita")),
        vr,
        as_text(row_get(r, "ds_fonte_receita", "fonte_recurso")),
        as_text(row_get(r, "ds_origem_receita", "tipo_receita")),
        as_text(row_get(r, "ds_especie_receita", "especie_recurso")),
        as_text(row_get(r, "ds_receita", "descricao_da_receita")),
        as_text(row_get(r, "nm_doador", "nome_do_doador")),
        as_text(row_get(r, "sg_partido_doador")),
    )


def map_despesa(ano: int, row: dict[str, str]) -> tuple | None:
    r = normalize_row(row)
    sq = as_int(row_get(r, "sq_candidato", "sequencial_candidato"))
    uf = (as_text(row_get(r, "sg_uf", "uf")) or "").upper()[:2] or None
    if uf and uf not in UFS_OK:
        return None
    vr = as_money(
        row_get(r, "vr_despesa_contratada", "vr_despesa", "valor_despesa")
    )
    if vr is None:
        return None
    return (
        ano,
        sq,
        uf,
        as_text(row_get(r, "sg_partido", "sigla_partido", "sigla__partido")),
        as_int(row_get(r, "nr_candidato", "numero_candidato")),
        as_text(row_get(r, "ds_cargo", "cargo")),
        as_text(row_get(r, "nm_candidato", "nome_candidato")),
        as_int(row_get(r, "sq_despesa")),
        as_date(row_get(r, "dt_despesa", "data_da_despesa")),
        vr,
        as_text(row_get(r, "ds_origem_despesa", "tipo_despesa")),
        as_text(row_get(r, "ds_despesa", "descricao_da_despesa", "descricao_da_despesa")),
        as_text(row_get(r, "nm_fornecedor", "nome_do_fornecedor")),
    )


def load_kind(url: str, ano: int, zpath: Path, kind: str) -> int:
    table = "eleicao.receita" if kind == "receita" else "eleicao.despesa"
    if kind == "receita":
        cols = """
          ano, sq_candidato, sg_uf, sg_partido, nr_candidato, ds_cargo, nm_candidato,
          sq_receita, dt_receita, vr_receita, ds_fonte, ds_origem, ds_especie, ds_receita,
          nm_doador, sg_partido_doador
        """
        mapper = map_receita
    else:
        cols = """
          ano, sq_candidato, sg_uf, sg_partido, nr_candidato, ds_cargo, nm_candidato,
          sq_despesa, dt_despesa, vr_despesa, ds_origem, ds_despesa, nm_fornecedor
        """
        mapper = map_despesa

    n = 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
                for name, reader in iter_members(zpath, kind):
                    for raw in reader:
                        mapped = mapper(ano, raw)
                        if mapped is None:
                            continue
                        copy.write_row(mapped)
                        n += 1
                        if n % 500_000 == 0:
                            print(f"    {kind} {ano} {n}", flush=True)
        conn.commit()
    return n


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_contas.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)
        conn.execute("TRUNCATE eleicao.receita, eleicao.despesa RESTART IDENTITY")

    anos = [int(a) for a in sys.argv[1:]] or [2014, 2016, 2018, 2020, 2022, 2024, 2026]
    tot_r = tot_d = 0
    for ano in anos:
        d = year_dir("br_cand_contas", ano)
        z = find_zip(d) if d.exists() else None
        if not z:
            print("skip contas", ano)
            continue
        print("contas", ano, z.name, round(z.stat().st_size / 1e6, 1), "MB", flush=True)
        nr = load_kind(url, ano, z, "receita")
        print("  receitas", nr, flush=True)
        nd = load_kind(url, ano, z, "despesa")
        print("  despesas", nd, flush=True)
        tot_r += nr
        tot_d += nd
    print("TOTAL receitas", tot_r, "despesas", tot_d, flush=True)


if __name__ == "__main__":
    main()
