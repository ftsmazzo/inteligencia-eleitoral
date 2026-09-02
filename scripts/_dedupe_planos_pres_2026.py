"""Remove duplicatas de planos presidente 2026 (seed + carga).

Mantém 1 doc por nome foldado: prefere o que tem sq_candidato e mais chunks.
"""
from __future__ import annotations

import os
import unicodedata

import psycopg


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().split())


def main() -> None:
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=False) as conn:
        rows = conn.execute(
            """
            SELECT id, nm_candidato, meta->>'sq_candidato' AS sq,
                   (SELECT count(*) FROM acervo.chunk ch WHERE ch.documento_id = d.id) AS n_chunks,
                   length(coalesce(fonte_orgao,'')) AS fonte_len
            FROM acervo.documento d
            WHERE tipo = 'plano_governo' AND ano_eleicao = 2026 AND cargo = 'presidente'
            """
        ).fetchall()
        by: dict[str, list] = {}
        for r in rows:
            key = fold(r[1])
            # normaliza aliases comuns
            aliases = {
                "LULA": "LUIZ INACIO LULA DA SILVA",
                "ZEMA": "ROMEU ZEMA",
                "ESCRITOR AUGUSTO CURY": "AUGUSTO JORGE CURY",
                "VETERINARIO WILSON GRASSI": "WILSON GRASSI",
                "CLARIANA BARAO": "CLARIANA BARAO",
                "SAMARA": "SAMARA MARTINS",
                "SAMARA MARTINS": "SAMARA MARTINS",
            }
            key = aliases.get(key, key)
            by.setdefault(key, []).append(r)

        to_del = []
        for key, group in by.items():
            if len(group) <= 1:
                continue
            # score: tem sq, mais chunks, fonte TSE
            def score(r):
                return (1 if r[2] else 0, r[3] or 0, r[4] or 0)

            group_sorted = sorted(group, key=score, reverse=True)
            keep = group_sorted[0]
            for r in group_sorted[1:]:
                to_del.append(r[0])
                print("DEL", r[1], r[0], "keep", keep[1])
        if not to_del:
            print("sem duplicatas")
            return
        for did in to_del:
            conn.execute("DELETE FROM acervo.chunk WHERE documento_id = %s", (did,))
            conn.execute("DELETE FROM acervo.documento WHERE id = %s", (did,))
        conn.commit()
        print("removidos", len(to_del))
        n = conn.execute(
            "SELECT count(*) FROM acervo.documento WHERE tipo='plano_governo' AND ano_eleicao=2026 AND cargo='presidente'"
        ).fetchone()[0]
        print("presidente restam", n)


if __name__ == "__main__":
    main()
