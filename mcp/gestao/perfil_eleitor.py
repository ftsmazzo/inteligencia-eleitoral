"""Perfil eleitoral territorial (UF + municípios) — Trilha A apenas.

Contrato: docs/PERFIL-ELEITOR.md
- NÃO usa voto do candidato da campanha.
- NÃO usa dossiê.
- Um único texto com âncora + apontamentos 2024 quando couber.
"""
from __future__ import annotations

from typing import Any

import psycopg

# Âncora da disputa por cargo (última urna do recorte).
_ANCORA_CARGO = {
    1: 2022,  # presidente
    3: 2022,  # governador
    5: 2022,  # senador
    6: 2022,  # dep. federal
    7: 2022,  # dep. estadual
    11: 2024,  # prefeito
    12: 2024,  # vice → trata como prefeito no mapa local
    13: 2024,  # vereador
}

_CARGOS_MUNICIPAIS = {11, 12, 13}


def _pct(part: int, total: int) -> str:
    if total <= 0:
        return "—"
    return f"{100.0 * part / total:.1f}%".replace(".", ",")


def _fmt_n(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _agrega_dim(
    conn: psycopg.Connection,
    ano: int,
    uf: str,
    coluna: str,
    cd_municipio_tse: int | None = None,
    top: int = 8,
) -> list[tuple[str, int]]:
    if coluna not in ("ds_genero", "ds_faixa_etaria", "ds_grau_escolaridade"):
        raise ValueError("dimensao invalida")
    mun_sql = ""
    params: list[Any] = [ano, uf]
    if cd_municipio_tse is not None:
        mun_sql = " AND cd_municipio_tse = %s"
        params.append(cd_municipio_tse)
    params.append(top)
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM({coluna}), ''), '(não informado)'),
               SUM(qt_eleitores)::bigint
        FROM eleicao.eleitorado
        WHERE ano = %s AND sg_uf = %s
          {mun_sql}
        GROUP BY 1
        ORDER BY 2 DESC NULLS LAST
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [(str(r[0]), int(r[1] or 0)) for r in rows]


def _total_eleitores(
    conn: psycopg.Connection, ano: int, uf: str, cd_municipio_tse: int | None = None
) -> int:
    mun_sql = ""
    params: list[Any] = [ano, uf]
    if cd_municipio_tse is not None:
        mun_sql = " AND cd_municipio_tse = %s"
        params.append(cd_municipio_tse)
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qt_eleitores)::bigint, 0)
        FROM eleicao.eleitorado
        WHERE ano = %s AND sg_uf = %s
          {mun_sql}
        """,
        params,
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _perfil_demo(
    conn: psycopg.Connection, ano: int, uf: str, cd_municipio_tse: int | None = None
) -> dict[str, Any]:
    total = _total_eleitores(conn, ano, uf, cd_municipio_tse)
    return {
        "ano": ano,
        "total": total,
        "genero": _agrega_dim(conn, ano, uf, "ds_genero", cd_municipio_tse),
        "faixa_etaria": _agrega_dim(conn, ano, uf, "ds_faixa_etaria", cd_municipio_tse, top=10),
        "escolaridade": _agrega_dim(conn, ano, uf, "ds_grau_escolaridade", cd_municipio_tse, top=10),
    }


def _linhas_demo(demo: dict[str, Any], *, prefix: str = "- ") -> list[str]:
    total = int(demo.get("total") or 0)
    if total <= 0:
        return [f"{prefix}Eleitorado {demo.get('ano')}: inexistente neste filtro."]
    out = [f"{prefix}Eleitorado {demo.get('ano')}: {_fmt_n(total)}."]
    for label, key in (
        ("Sexo", "genero"),
        ("Faixa etária", "faixa_etaria"),
        ("Escolaridade", "escolaridade"),
    ):
        pares = demo.get(key) or []
        if not pares:
            out.append(f"{prefix}{label}: inexistente.")
            continue
        trecho = "; ".join(f"{n} {_pct(q, total)} ({_fmt_n(q)})" for n, q in pares[:5])
        out.append(f"{prefix}{label}: {trecho}.")
    return out


def _turno_final(conn: psycopg.Connection, ano: int, cd_cargo: int, uf: str) -> int:
    row = conn.execute(
        """
        SELECT MAX(nr_turno)::int
        FROM eleicao.votacao
        WHERE ano = %s AND cd_cargo = %s AND sg_uf = %s
        """,
        (ano, cd_cargo, uf),
    ).fetchone()
    return int(row[0] or 1) if row and row[0] else 1


def _campeao_uf(
    conn: psycopg.Connection, ano: int, cd_cargo: int, uf: str
) -> dict[str, Any] | None:
    """Partido/candidato eleito na UF (situação de urna)."""
    row = conn.execute(
        """
        SELECT MAX(v.sg_partido), MAX(v.nm_urna), SUM(v.qt_votos)::bigint, MAX(v.nr_turno)
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s
          AND api._eh_eleito(v.ds_sit_tot_turno)
        GROUP BY v.sq_candidato
        ORDER BY SUM(v.qt_votos) DESC NULLS LAST
        LIMIT 1
        """,
        (ano, cd_cargo, uf),
    ).fetchone()
    if not row:
        return None
    return {
        "partido": row[0] or "",
        "nome": row[1] or "",
        "votos": int(row[2] or 0),
        "turno": int(row[3] or 1),
        "modo": "eleito_urna",
    }


def _campeao_mun(
    conn: psycopg.Connection,
    ano: int,
    cd_cargo: int,
    uf: str,
    cd_municipio_tse: int,
    nr_turno: int,
) -> dict[str, Any] | None:
    """Quem teve mais votos naquele município (campeão local do cargo)."""
    row = conn.execute(
        """
        SELECT v.sg_partido, v.nm_urna, SUM(v.qt_votos)::bigint
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s
          AND v.cd_municipio_tse = %s AND v.nr_turno = %s
        GROUP BY v.sq_candidato, v.sg_partido, v.nm_urna
        ORDER BY SUM(v.qt_votos) DESC NULLS LAST
        LIMIT 1
        """,
        (ano, cd_cargo, uf, cd_municipio_tse, nr_turno),
    ).fetchone()
    if not row:
        return None
    return {
        "partido": row[0] or "",
        "nome": row[1] or "",
        "votos": int(row[2] or 0),
        "turno": nr_turno,
        "modo": "mais_votado_local",
    }


def _prefeito_eleito_mun(
    conn: psycopg.Connection, uf: str, cd_municipio_tse: int
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT MAX(v.sg_partido), MAX(v.nm_urna), SUM(v.qt_votos)::bigint
        FROM eleicao.votacao v
        WHERE v.ano = 2024 AND v.cd_cargo = 11 AND v.sg_uf = %s
          AND v.cd_municipio_tse = %s
          AND api._eh_eleito(v.ds_sit_tot_turno)
        GROUP BY v.sq_candidato
        ORDER BY SUM(v.qt_votos) DESC NULLS LAST
        LIMIT 1
        """,
        (uf, cd_municipio_tse),
    ).fetchone()
    if not row:
        return None
    return {"partido": row[0] or "", "nome": row[1] or "", "votos": int(row[2] or 0)}


def _top_municipios(
    conn: psycopg.Connection, ano: int, uf: str, limite: int = 8
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.cd_municipio_tse,
               COALESCE(m.nome, e.cd_municipio_tse::text),
               SUM(e.qt_eleitores)::bigint
        FROM eleicao.eleitorado e
        LEFT JOIN ref.municipio m ON m.cd_municipio_tse = e.cd_municipio_tse
        WHERE e.ano = %s AND e.sg_uf = %s
        GROUP BY e.cd_municipio_tse, m.nome
        ORDER BY SUM(e.qt_eleitores) DESC NULLS LAST
        LIMIT %s
        """,
        (ano, uf, limite),
    ).fetchall()
    return [
        {"cd_municipio_tse": int(r[0]), "nome": r[1], "eleitores": int(r[2] or 0)}
        for r in rows
    ]


def _delta_shares(
    a: list[tuple[str, int]], b: list[tuple[str, int]], total_a: int, total_b: int
) -> list[str]:
    """Aponta mudanças de participação (pp) entre dois anos — só categorias presentes."""
    if total_a <= 0 or total_b <= 0:
        return []
    map_a = {k: v for k, v in a}
    map_b = {k: v for k, v in b}
    keys = set(map_a) | set(map_b)
    deltas: list[tuple[float, str]] = []
    for k in keys:
        pa = 100.0 * map_a.get(k, 0) / total_a
        pb = 100.0 * map_b.get(k, 0) / total_b
        d = pb - pa
        if abs(d) >= 1.5:  # limiar mínimo para não poluir
            deltas.append((d, f"{k}: {pa:.1f}% → {pb:.1f}% ({d:+.1f} p.p.)".replace(".", ",")))
    deltas.sort(key=lambda x: abs(x[0]), reverse=True)
    return [t for _, t in deltas[:5]]


def montar_perfil_eleitor(
    conn: psycopg.Connection,
    *,
    uf: str,
    cd_cargo: int,
    cargo_label: str,
) -> dict[str, Any]:
    if not uf:
        raise ValueError("UF obrigatória para Perfil eleitoral")

    cargo_mapa = 11 if cd_cargo == 12 else cd_cargo
    ano_ancora = _ANCORA_CARGO.get(cargo_mapa) or 2022
    municipal = cargo_mapa in _CARGOS_MUNICIPAIS

    demo_uf = _perfil_demo(conn, ano_ancora, uf)
    campeao_uf = _campeao_uf(conn, ano_ancora, cargo_mapa, uf)
    turno = _turno_final(conn, ano_ancora, cargo_mapa, uf)
    muns = _top_municipios(conn, ano_ancora, uf, limite=8)

    # 2024 só como apontamento quando a âncora NÃO é 2024 (disputa estadual/federal).
    apontar_2024 = (not municipal) and ano_ancora != 2024
    demo_uf_2024 = _perfil_demo(conn, 2024, uf) if apontar_2024 else None

    linhas: list[str] = [
        f"Perfil eleitoral — {uf} · âncora {ano_ancora} ({cargo_label}).",
        "Fonte: Trilha A (eleicao.eleitorado + eleicao.votacao). "
        "Não usa dossiê nem voto do candidato da campanha.",
        "Partido campeão no estado = eleito na urna. "
        "Nos municípios = mais votado naquele local no turno considerado.",
        "",
        f"## Estado ({uf})",
    ]
    linhas.extend(_linhas_demo(demo_uf))
    if campeao_uf:
        linhas.append(
            f"- Partido campeão {ano_ancora} ({cargo_label}): {campeao_uf['partido']} — "
            f"{campeao_uf['nome']} ({_fmt_n(campeao_uf['votos'])} votos, "
            f"turno {campeao_uf['turno']}, {campeao_uf['modo']})."
        )
    else:
        linhas.append(f"- Partido campeão {ano_ancora} ({cargo_label}): inexistente neste filtro.")

    if apontar_2024 and demo_uf_2024 and demo_uf_2024.get("total"):
        linhas += ["", "### Apontamentos 2024 (urna/cadastro municipal — não substitui a âncora estadual)"]
        t0, t1 = demo_uf["total"], demo_uf_2024["total"]
        if t0 and t1:
            var = 100.0 * (t1 - t0) / t0
            linhas.append(
                f"- Eleitorado UF: {_fmt_n(t0)} ({ano_ancora}) → {_fmt_n(t1)} (2024) "
                f"({var:+.1f}%).".replace(".", ",")
            )
        for titulo, key in (
            ("Sexo", "genero"),
            ("Faixa etária", "faixa_etaria"),
            ("Escolaridade", "escolaridade"),
        ):
            deltas = _delta_shares(
                demo_uf.get(key) or [],
                demo_uf_2024.get(key) or [],
                int(demo_uf.get("total") or 0),
                int(demo_uf_2024.get("total") or 0),
            )
            if deltas:
                linhas.append(f"- Mudanças relevantes · {titulo}: " + "; ".join(deltas))

    linhas += ["", "## Municípios (maiores eleitorados na âncora)"]
    for mun in muns:
        cd = mun["cd_municipio_tse"]
        demo_m = _perfil_demo(conn, ano_ancora, uf, cd)
        camp_m = _campeao_mun(conn, ano_ancora, cargo_mapa, uf, cd, turno)
        linhas.append(f"### {mun['nome']}")
        linhas.extend(_linhas_demo(demo_m))
        if camp_m:
            linhas.append(
                f"- Campeão local {ano_ancora} ({cargo_label}): {camp_m['partido']} — "
                f"{camp_m['nome']} ({_fmt_n(camp_m['votos'])} votos, turno {camp_m['turno']})."
            )
        else:
            linhas.append(f"- Campeão local {ano_ancora}: inexistente neste filtro.")

        if apontar_2024:
            demo_m24 = _perfil_demo(conn, 2024, uf, cd)
            pref = _prefeito_eleito_mun(conn, uf, cd)
            bits = []
            if demo_m.get("total") and demo_m24.get("total"):
                bits.append(
                    f"eleitorado {_fmt_n(demo_m['total'])} → {_fmt_n(demo_m24['total'])}"
                )
            if pref:
                bits.append(
                    f"prefeito 2024: {pref['partido']} — {pref['nome']} "
                    f"({_fmt_n(pref['votos'])} votos)"
                )
            if bits:
                linhas.append("- Apontamento 2024: " + "; ".join(bits) + ".")

    linhas += [
        "",
        "## Nota de leitura",
        "- Este bloco descreve o eleitorado do território e quem venceu o cargo no local.",
        "- Não afirma quem é o eleitor do candidato da campanha.",
    ]
    if apontar_2024:
        linhas.append(
            "- 2024 entra só como comparação/apontamento (prefeitura e cadastro); "
            "não substitui o perfil da disputa estadual/federal da âncora."
        )

    return {
        "titulo": f"Perfil eleitoral — {uf} · {ano_ancora}",
        "corpo": "\n".join(linhas),
        "fonte": "eleicao.eleitorado + eleicao.votacao (Trilha A)",
        "nivel": "fato",
        "meta": {
            "contrato": "perfil_eleitor_v2",
            "uf": uf,
            "ano_ancora": ano_ancora,
            "cd_cargo": cargo_mapa,
            "apontamentos_2024": apontar_2024,
            "municipios": len(muns),
            "campeao_uf": campeao_uf,
        },
    }
