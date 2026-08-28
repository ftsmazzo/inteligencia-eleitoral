"""Gera fichas territoriais (Trilha B) a partir da Trilha A no Postgres.

Uso:
  python scripts/gerar_fichas_territoriais.py
  python scripts/gerar_fichas_territoriais.py --uf CE --ano 2022
  python scripts/gerar_fichas_territoriais.py --so-seed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import date
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, dsn, load_env

SEED_DIR = ROOT / "mcp" / "seed"
SEED_JSONL = SEED_DIR / "acervo_fichas_territoriais.jsonl"
UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


def _texto_ficha(conn: psycopg.Connection, uf: str, ano: int) -> str:
    row = conn.execute(
        """
        SELECT
          count(DISTINCT v.sq_candidato) FILTER (WHERE v.cd_cargo = 6) AS n_cand_dep,
          count(DISTINCT v.sq_candidato) FILTER (WHERE v.cd_cargo = 3 AND api._eh_eleito(v.ds_sit_tot_turno)) AS n_eleitos_gov,
          sum(v.qt_votos) FILTER (WHERE v.cd_cargo = 3 AND v.nr_turno = 1)::bigint AS votos_gov_t1
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.sg_uf = %s
        """,
        (ano, uf),
    ).fetchone()
    ele = conn.execute(
        """
        SELECT sg_partido, count(*)::int AS n
        FROM (
          SELECT DISTINCT ON (sq_candidato) sq_candidato, sg_partido
          FROM eleicao.votacao
          WHERE ano = %s AND sg_uf = %s AND cd_cargo = 6 AND api._eh_eleito(ds_sit_tot_turno)
        ) t
        GROUP BY 1 ORDER BY n DESC LIMIT 5
        """,
        (ano, uf),
    ).fetchall()
    eleitorado = conn.execute(
        """
        SELECT sum(qt_eleitores)::bigint FROM eleicao.eleitorado
        WHERE ano = %s AND sg_uf = %s
        """,
        (ano, uf),
    ).fetchone()[0]

    partes = [
        f"# Perfil eleitoral {uf} · urna {ano}",
        "",
        f"Eleitorado cadastrado (perfil TSE, soma municipal): {eleitorado or 0:,} eleitores.",
        f"Candidatos a deputado federal distintos na urna: {row[0] or 0}.",
        f"Governador eleito (turno registrado): {row[1] or 0}.",
        f"Votos nominais 1º turno governador (soma UF): {row[2] or 0:,}.",
        "",
        "## Top partidos — cadeiras deputado federal",
    ]
    if ele:
        for sg, n in ele:
            partes.append(f"- {sg}: {n} eleito(s)")
    else:
        partes.append("- (sem eleitos federais no filtro)")
    partes.append("")
    partes.append(
        "Fonte: Trilha A (eleicao.votacao, eleicao.eleitorado). "
        "Texto derivado para consulta semântica — cifras devem ser confirmadas via api.eleitos/votacao."
    )
    return "\n".join(partes)


def gerar_docs(conn: psycopg.Connection, ufs: list[str], ano: int) -> list[dict]:
    docs: list[dict] = []
    for uf in ufs:
        body = _texto_ficha(conn, uf, ano)
        digest = hashlib.sha256(f"ficha_{uf}_{ano}_{body[:200]}".encode()).hexdigest()
        docs.append(
            {
                "tipo": "ficha_territorial",
                "titulo": f"Ficha territorial {uf} · {ano}",
                "descricao": f"Perfil eleitoral derivado da urna {ano} para {uf}.",
                "nivel": "referencia",
                "ano_eleicao": ano,
                "vigencia_inicio": f"{ano}-01-01",
                "vigencia_fim": f"{ano}-12-31",
                "escopo": "UF",
                "sg_uf": uf,
                "sg_partido": None,
                "nm_candidato": None,
                "cargo": None,
                "tags": ["ficha_territorial", uf, str(ano)],
                "fonte_orgao": "Derivado Trilha A · TSE",
                "sha256": digest,
                "id_base_raw": "acervo_ficha_territorial",
                "meta": {"uf": uf, "ano": ano, "gerado_em": date.today().isoformat()},
                "chunks": [{"ord": 0, "secao": f"Perfil {uf}", "texto": body}],
            }
        )
        print("ficha", uf, ano)
    return docs


def escrever_seed(docs: list[dict]) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with SEED_JSONL.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print("seed", SEED_JSONL, "docs", len(docs))


def carregar_db(docs: list[dict]) -> None:
    from carregar_acervo_planos import carregar_db as _load  # noqa: WPS433

    _load(docs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", action="append", help="UF (repita para várias). Default: todas.")
    ap.add_argument("--ano", type=int, default=2022)
    ap.add_argument("--so-seed", action="store_true")
    args = ap.parse_args()
    ufs = [u.upper() for u in args.uf] if args.uf else UFS

    load_env()
    with psycopg.connect(dsn()) as conn:
        docs = gerar_docs(conn, ufs, args.ano)
    escrever_seed(docs)
    if args.so_seed:
        return
    try:
        carregar_db(docs)
    except Exception as e:
        print("AVISO: DB local indisponível — seed gerado para bootstrap:", e)


if __name__ == "__main__":
    main()
