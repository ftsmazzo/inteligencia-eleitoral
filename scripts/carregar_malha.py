"""Carga ref.municipio a partir da malha IBGE em data/raw."""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MALHA = ROOT / "data" / "raw" / "br_mun_malha_ibge" / "ano=estatica" / "municipios.json"


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Defina DATABASE_URL")
    data = json.loads(MALHA.read_text(encoding="utf-8"))
    rows = []
    for m in data:
        imediata = m.get("regiao-imediata") or {}
        inter = (imediata.get("regiao-intermediaria") or {}) if isinstance(imediata, dict) else {}
        micro = m.get("microrregiao") or {}
        meso = (micro.get("mesorregiao") or {}) if isinstance(micro, dict) else {}
        uf = (meso.get("UF") or inter.get("UF") or {}) if isinstance(meso, dict) else (inter.get("UF") or {})
        reg = uf.get("regiao") or {}
        sg = uf.get("sigla")
        if not sg:
            continue
        rows.append(
            (
                int(m["id"]),
                m["nome"],
                sg,
                meso.get("nome"),
                micro.get("nome") if isinstance(micro, dict) else None,
                reg.get("nome") or "",
            )
        )
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE ref.municipio")
            cur.executemany(
                """
                INSERT INTO ref.municipio (cod_ibge, nome, sg_uf, mesorregiao, microrregiao, regiao)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COUNT(DISTINCT sg_uf) FROM ref.municipio")
            print("municipios", cur.fetchone())


if __name__ == "__main__":
    main()
