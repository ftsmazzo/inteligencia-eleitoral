"""Auditoria do recorte SPEC-BRASIL: raw + Postgres.

Gate bloqueante: nenhum módulo posterior (contexto, parlamento, entrega MCP)
deve avançar enquanto este script retornar exit code 1.

Uso:
  python scripts/auditar_recorte.py
  python scripts/auditar_recorte.py --json
  python scripts/auditar_recorte.py --write-docs
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tse_util import RAW, dsn, find_zip, load_env, year_dir  # noqa: E402

FEDERAL = (2014, 2018, 2022)
MUNICIPAL = (2016, 2020, 2024)
NUCLEO_ANOS = (*FEDERAL, *MUNICIPAL)
CAND_ANOS = (*NUCLEO_ANOS, 2026)
ELEITORADO_ANOS = (*NUCLEO_ANOS, 2026)

MIN_MUN_FED = 5560
MIN_MUN_MUN = 5550
MIN_UF_FED = 27
MIN_UF_MUN = 26
MIN_MALHA = 5565


@dataclass
class Check:
    bloco: str
    item: str
    status: str  # ok | falha | aviso
    detalhe: str


def raw_ano(id_base: str, ano: int) -> bool:
    d = year_dir(id_base, ano)
    return d.is_dir() and (find_zip(d) is not None or any(d.glob("*.csv")))


def raw_malha() -> bool:
    d = RAW / "br_mun_malha_ibge"
    if not d.is_dir():
        return False
    for sub in ("ano=estatica", "estatica"):
        p = d / sub
        if p.is_dir() and (any(p.glob("*.json")) or any(p.glob("*.csv"))):
            return True
    return any(d.rglob("municipios.json"))


def pg_stats(conn: psycopg.Connection, table: str, ano_col: str = "ano") -> dict[int, dict]:
    q = f"""
        SELECT {ano_col} AS ano,
               count(*)::bigint AS n,
               count(DISTINCT sg_uf)::int AS ufs,
               count(DISTINCT cd_municipio_tse)::int AS muns
        FROM {table}
        GROUP BY 1
    """
    try:
        rows = conn.execute(q).fetchall()
    except Exception:
        return {}
    out: dict[int, dict] = {}
    for ano, n, ufs, muns in rows:
        out[int(ano)] = {"n": int(n), "ufs": int(ufs or 0), "muns": int(muns or 0)}
    return out


def pg_count_by_ano(conn: psycopg.Connection, table: str, schema: str = "eleicao") -> dict[int, int]:
    try:
        rows = conn.execute(
            f"SELECT ano, count(*)::bigint FROM {schema}.{table} GROUP BY 1"
        ).fetchall()
    except Exception:
        return {}
    return {int(a): int(n) for a, n in rows}


def audit_raw(checks: list[Check]) -> None:
    packs = [
        ("br_mun_votacao_nominal", NUCLEO_ANOS),
        ("br_mun_detalhe_apuracao", NUCLEO_ANOS),
        ("br_cand_nominata", CAND_ANOS),
        ("br_mun_eleitorado_perfil", ELEITORADO_ANOS),
        ("br_cand_coligacao", CAND_ANOS),
    ]
    for id_base, anos in packs:
        for ano in anos:
            ok = raw_ano(id_base, ano)
            checks.append(
                Check(
                    "raw",
                    f"{id_base}/{ano}",
                    "ok" if ok else "falha",
                    "origem.zip ou csv" if ok else "pacote ausente em data/raw",
                )
            )
    ok = raw_malha()
    checks.append(
        Check(
            "raw",
            "br_mun_malha_ibge",
            "ok" if ok else "falha",
            "malha presente" if ok else "malha ausente",
        )
    )


def audit_pg(conn: psycopg.Connection, checks: list[Check]) -> None:
    vot = pg_stats(conn, "eleicao.votacao")
    det = pg_stats(conn, "eleicao.detalhe_munzona")
    cand = pg_stats(conn, "eleicao.candidatura")
    ele = pg_stats(conn, "eleicao.eleitorado")
    col = pg_count_by_ano(conn, "coligacao")
    malha = conn.execute("SELECT count(*) FROM ref.municipio").fetchone()[0]

    for ano in NUCLEO_ANOS:
        federal = ano in FEDERAL
        min_uf = MIN_UF_FED if federal else MIN_UF_MUN
        min_mun = MIN_MUN_FED if federal else MIN_MUN_MUN
        min_vot = 5_000_000 if federal else 500_000
        min_det = 30_000 if federal else 10_000
        min_cand = 20_000 if federal else 300_000
        min_ele = 1_000_000
        min_col = 1_000

        for label, data, rules in (
            ("votacao", vot.get(ano), (min_vot, min_uf, min_mun)),
            ("detalhe", det.get(ano), (min_det, min_uf, None)),
            ("candidatura", cand.get(ano), (min_cand, min_uf, None)),
            ("eleitorado", ele.get(ano), (min_ele, min_uf, None)),
        ):
            min_n, min_u, min_m = rules
            if not data:
                checks.append(
                    Check("postgres", f"{label}/{ano}", "falha", "sem linhas no banco")
                )
                continue
            ok = data["n"] >= min_n and data["ufs"] >= min_u
            if min_m is not None:
                ok = ok and data["muns"] >= min_m
            checks.append(
                Check(
                    "postgres",
                    f"{label}/{ano}",
                    "ok" if ok else "falha",
                    f"n={data['n']:,} uf={data['ufs']} mun={data.get('muns', '—')}",
                )
            )

        cn = col.get(ano, 0)
        checks.append(
            Check(
                "postgres",
                f"coligacao/{ano}",
                "ok" if cn >= min_col else "falha",
                f"n={cn:,}",
            )
        )

    checks.append(
        Check(
            "postgres",
            "ref.municipio",
            "ok" if malha >= MIN_MALHA else "falha",
            f"n={malha:,}",
        )
    )


def audit_api_smoke(conn: psycopg.Connection, checks: list[Check]) -> None:
    """Regressão: nominata dep. federal + cod_ibge não pode voltar vazio se há chapa na UF."""
    try:
        r = conn.execute(
            "SELECT api.nominata(%s, %s, %s, %s, %s, NULL, NULL, NULL, %s)",
            (2026, "deputado_federal", "SP", 3554102, "PRD", 5),
        ).fetchone()[0]
        n = len(r.get("linhas") or [])
        ok = r.get("status") == "ok" and n >= 1
        checks.append(
            Check(
                "api_smoke",
                "nominata_dep_federal_uf_com_cod_ibge",
                "ok" if ok else "falha",
                f"status={r.get('status')} linhas={n} (esperado PRD SP 2026 mesmo com ibge Taubaté)",
            )
        )
    except Exception as e:
        checks.append(
            Check(
                "api_smoke",
                "nominata_dep_federal_uf_com_cod_ibge",
                "falha",
                str(e)[:200],
            )
        )


def audit_modulos_posteriores(conn: psycopg.Connection, checks: list[Check]) -> None:
    """Complementos: aviso se vazio, ok se carregado."""
    packs = [
        ("contexto", "populacao_mun", 5000, "populacao"),
        ("contexto", "cadunico_mun", 1000, "cadunico"),
        ("contexto", "bolsa_familia_mun", 1000, "bolsa_familia"),
        ("eleicao", "bem", 10000, "bens"),
        ("eleicao", "rede_social", 100000, "rede_social"),
        ("eleicao", "candidato_complementar", 100000, "candidato_complementar"),
        ("eleicao", "receita", 10000, "contas_receita"),
        ("eleicao", "despesa", 10000, "contas_despesa"),
        ("parlamentar", "deputado", 400, "camara_deputados"),
        ("parlamentar", "proposicao", 1000, "camara_proposicoes"),
        ("acervo", "documento", 5000, "acervo_docs"),
        ("acervo", "chunk", 10, "acervo_chunks"),
    ]
    for schema, table, min_n, label in packs:
        try:
            n = conn.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
        except Exception:
            n = 0
        checks.append(
            Check(
                "complemento",
                label,
                "ok" if n >= min_n else "aviso",
                f"n={n:,}" if n else "vazio — rode carregar_complementos.py / seeds acervo",
            )
        )


def render_md(checks: list[Check], nucleus_ok: bool) -> str:
    hoje = date.today().isoformat()
    falhas = [c for c in checks if c.status == "falha"]
    lines = [
        f"# Auditoria do recorte · {hoje}",
        "",
        "**Fonte da verdade operacional.** Rode `python scripts/auditar_recorte.py` antes de qualquer carga, deploy ou módulo novo.",
        "",
        f"**Núcleo eleitoral:** {'PASSOU' if nucleus_ok else 'BLOQUEADO'}",
        "",
        "## Regra de gate",
        "",
        "1. `auditar_recorte.py` exit 0 → pode carregar complementos e redeploy MCP.",
        "2. Exit 1 → **proibido** IBGE, social, Parlamento, entrega ao usuário.",
        "3. `docs/INVENTARIO-INBOX.md` é índice do despejo; **status de carga** é só esta página + o script.",
        "",
        "## Matriz (última execução)",
        "",
        "| Bloco | Item | Status | Detalhe |",
        "|---|---|---|---|",
    ]
    for c in checks:
        if c.bloco in ("modulo_posterior", "complemento"):
            continue
        lines.append(f"| {c.bloco} | {c.item} | {c.status} | {c.detalhe} |")
    if falhas:
        lines.extend(["", "## Falhas bloqueantes", ""])
        for c in falhas:
            lines.append(f"- **{c.bloco}/{c.item}**: {c.detalhe}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-docs", action="store_true")
    args = parser.parse_args()

    load_env()
    checks: list[Check] = []
    audit_raw(checks)

    with psycopg.connect(dsn()) as conn:
        audit_pg(conn, checks)
        audit_api_smoke(conn, checks)
        audit_modulos_posteriores(conn, checks)

    nucleus_checks = [c for c in checks if c.bloco in ("raw", "postgres")]
    nucleus_ok = all(c.status == "ok" for c in nucleus_checks)
    falhas = [c for c in checks if c.status == "falha"]

    if args.json:
        print(
            json.dumps(
                {
                    "nucleus_ok": nucleus_ok,
                    "falhas": len(falhas),
                    "checks": [asdict(c) for c in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Nucleo: {'OK' if nucleus_ok else 'BLOQUEADO'} ({len(falhas)} falha(s))")
        for c in checks:
            if c.bloco == "modulo_posterior":
                continue
            mark = {"ok": "+", "falha": "!", "aviso": "~"}.get(c.status, "?")
            print(f"  [{mark}] {c.bloco}/{c.item}: {c.detalhe}")

    if args.write_docs:
        out = ROOT / "docs" / "AUDITORIA-RECORTE.md"
        out.write_text(render_md(checks, nucleus_ok), encoding="utf-8")
        print(f"Escrito {out}")

    return 0 if nucleus_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
