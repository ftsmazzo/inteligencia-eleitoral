"""Trajetória narrativa do candidato da campanha — só Trilha A.

Contrato:
- Sujeito = candidato do escopo Gestão (ex.: CARLOS CLEY), nunca o adversário por engano.
- 2026 = candidatura atual (sem resultado de urna).
- Anos com urna: eleito / derrotado (com campeão e diferença de votos quando houver).
- Vice: resultado da chapa de prefeito no município.
- Sem histórico: frase seca de primeira candidatura.
"""
from __future__ import annotations

from typing import Any

import psycopg

_ANOS_URNA = (2024, 2022, 2020, 2018, 2016, 2014)


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _nome_mun(conn: psycopg.Connection, cd_municipio_tse: int | None) -> str | None:
    if not cd_municipio_tse:
        return None
    row = conn.execute(
        "SELECT nome FROM ref.municipio WHERE cd_municipio_tse = %s LIMIT 1",
        (cd_municipio_tse,),
    ).fetchone()
    return row[0] if row else str(cd_municipio_tse)


def _sq_prefeito_chapa(
    conn: psycopg.Connection,
    ano: int,
    uf: str,
    cd_municipio_tse: int | None,
    partido: str | None,
) -> tuple[int, str] | None:
    """Só aceita chapa do mesmo partido — sem chute em outro prefeito do município."""
    if not cd_municipio_tse or not partido:
        return None
    row = conn.execute(
        """
        SELECT c.sq_candidato, c.nm_urna
        FROM eleicao.candidatura c
        WHERE c.ano = %s AND c.sg_uf = %s AND c.cd_municipio_tse = %s
          AND c.cd_cargo = 11 AND upper(c.sg_partido) = upper(%s)
        ORDER BY c.sq_candidato
        LIMIT 1
        """,
        (ano, uf, cd_municipio_tse, partido),
    ).fetchone()
    if row:
        return int(row[0]), row[1] or ""
    return None


def _resultado_urna(
    conn: psycopg.Connection,
    *,
    ano: int,
    cd_cargo: int,
    uf: str,
    sq: int,
    cd_municipio_tse: int | None,
) -> dict[str, Any]:
    """Situação e votos do candidato; se derrotado, campeão local/UF e margem."""
    cargo_votos = 11 if cd_cargo == 12 else cd_cargo
    sq_votos = sq
    nota_chapa = None
    if cd_cargo == 12:
        chapa = _sq_prefeito_chapa(conn, ano, uf, cd_municipio_tse, None)
        # tenta de novo com partido no caller; aqui só sq do próprio se não achar
        if chapa:
            sq_votos, nm_p = chapa
            nota_chapa = nm_p

    # votos + situação do próprio (ou chapa)
    row = conn.execute(
        """
        SELECT COALESCE(SUM(v.qt_votos), 0)::bigint,
               MAX(v.ds_sit_tot_turno),
               MAX(v.nr_turno),
               MAX(v.nm_urna),
               MAX(v.sg_partido)
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s AND v.sq_candidato = %s
        """,
        (ano, cargo_votos, uf, sq_votos),
    ).fetchone()
    votos = int(row[0] or 0) if row else 0
    sit = (row[1] or "") if row else ""
    turno = int(row[2] or 1) if row and row[2] else 1
    nm_urna_v = (row[3] or "") if row else ""
    partido_v = (row[4] or "") if row else ""

    eleito = False
    if sit:
        er = conn.execute("SELECT api._eh_eleito(%s)", (sit,)).fetchone()
        eleito = bool(er and er[0])

    out: dict[str, Any] = {
        "votos": votos,
        "situacao": sit or None,
        "turno": turno,
        "eleito": eleito,
        "sq_votos": sq_votos,
        "nota_chapa": nota_chapa,
        "nm_urna_votos": nm_urna_v,
        "partido_votos": partido_v,
        "vencedor": None,
    }

    if eleito or votos <= 0:
        return out

    # campeão no mesmo pleito / local
    mun_sql = ""
    params: list[Any] = [ano, cargo_votos, uf, turno]
    if cargo_votos in (11, 12, 13) and cd_municipio_tse:
        mun_sql = " AND v.cd_municipio_tse = %s"
        params.append(cd_municipio_tse)
    params.append(sq_votos)
    win = conn.execute(
        f"""
        SELECT v.nm_urna, v.sg_partido, SUM(v.qt_votos)::bigint,
               bool_or(api._eh_eleito(v.ds_sit_tot_turno))
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s AND v.nr_turno = %s
          {mun_sql}
          AND v.sq_candidato <> %s
        GROUP BY v.sq_candidato, v.nm_urna, v.sg_partido
        ORDER BY bool_or(api._eh_eleito(v.ds_sit_tot_turno)) DESC,
                 SUM(v.qt_votos) DESC NULLS LAST
        LIMIT 1
        """,
        params,
    ).fetchone()
    if win:
        vwin = int(win[2] or 0)
        out["vencedor"] = {
            "nome": win[0] or "",
            "partido": win[1] or "",
            "votos": vwin,
            "eleito": bool(win[3]),
            "margem": max(0, vwin - votos),
        }
    return out


def _listar_candidaturas(
    conn: psycopg.Connection,
    *,
    nm_urna: str,
    nm_candidato: str,
    uf: str | None,
    sq_atual: int | None,
) -> list[dict[str, Any]]:
    """Candidaturas do mesmo personagem — prioriza urna/nome do escopo; evita homônimo frouxo."""
    nomes = []
    for n in (nm_urna, nm_candidato):
        n = (n or "").strip()
        if n and n.upper() not in {x.upper() for x in nomes}:
            nomes.append(n)
    if not nomes:
        return []

    # match: nm_urna igual OU (nm_candidato igual) — sem ILIKE frouxo de tokens
    clauses = []
    params: list[Any] = []
    for n in nomes:
        clauses.append("(upper(c.nm_urna) = upper(%s) OR upper(c.nm_candidato) = upper(%s))")
        params.extend([n, n])
    where_nome = "(" + " OR ".join(clauses) + ")"
    uf_sql = ""
    if uf:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)

    rows = conn.execute(
        f"""
        SELECT c.ano, c.cd_cargo, r.nome AS cargo, c.sg_uf, c.nm_urna, c.nm_candidato,
               c.sg_partido, c.ds_situacao, c.sq_candidato, c.nr_candidato, c.cd_municipio_tse
        FROM eleicao.candidatura c
        JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
        WHERE {where_nome}
          {uf_sql}
          AND c.ano IN (2014, 2016, 2018, 2020, 2022, 2024, 2026)
        ORDER BY c.ano DESC, c.cd_cargo
        LIMIT 40
        """,
        params,
    ).fetchall()
    out = [
        {
            "ano": int(r[0]),
            "cd_cargo": int(r[1]),
            "cargo": r[2],
            "sg_uf": r[3],
            "nm_urna": r[4],
            "nm_candidato": r[5],
            "sg_partido": r[6],
            "ds_situacao": r[7],
            "sq_candidato": int(r[8]),
            "nr_candidato": r[9],
            "cd_municipio_tse": r[10],
        }
        for r in rows
    ]
    # se sq atual não veio na lista (nome divergente), inclui a linha 2026 do sq
    if sq_atual and not any(x["sq_candidato"] == sq_atual for x in out):
        row = conn.execute(
            """
            SELECT c.ano, c.cd_cargo, r.nome, c.sg_uf, c.nm_urna, c.nm_candidato,
                   c.sg_partido, c.ds_situacao, c.sq_candidato, c.nr_candidato, c.cd_municipio_tse
            FROM eleicao.candidatura c
            JOIN ref.cargo r ON r.cd_cargo = c.cd_cargo
            WHERE c.sq_candidato = %s
            ORDER BY c.ano DESC
            LIMIT 5
            """,
            (sq_atual,),
        ).fetchall()
        for r in row:
            out.append(
                {
                    "ano": int(r[0]),
                    "cd_cargo": int(r[1]),
                    "cargo": r[2],
                    "sg_uf": r[3],
                    "nm_urna": r[4],
                    "nm_candidato": r[5],
                    "sg_partido": r[6],
                    "ds_situacao": r[7],
                    "sq_candidato": int(r[8]),
                    "nr_candidato": r[9],
                    "cd_municipio_tse": r[10],
                }
            )
    # dedup ano+cargo+sq
    seen = set()
    uniq = []
    for t in out:
        k = (t["ano"], t["cd_cargo"], t["sq_candidato"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    uniq.sort(key=lambda x: (-x["ano"], x["cd_cargo"]))
    return uniq


def montar_trajetoria(
    conn: psycopg.Connection,
    *,
    st: dict[str, Any],
) -> dict[str, Any]:
    nome = st.get("nm_urna") or st.get("nm_candidato") or "Candidato"
    nm_cand = st.get("nm_candidato") or nome
    uf = st.get("sg_uf")
    partido_atual = st.get("sg_partido") or "—"
    cargo_atual = st.get("cargo_label") or str(st.get("cd_cargo") or "")
    sq_atual = int(st["sq_candidato"]) if st.get("sq_candidato") else None
    ano_ref = int(st.get("ano_ref") or 2026)

    traj = _listar_candidaturas(
        conn,
        nm_urna=nome,
        nm_candidato=nm_cand,
        uf=uf if st.get("cd_cargo") != 1 else None,
        sq_atual=sq_atual,
    )

    # enriquecer histórico com urna
    historico: list[dict[str, Any]] = []
    for t in traj:
        item = dict(t)
        item["municipio"] = _nome_mun(conn, t.get("cd_municipio_tse"))
        if int(t["ano"]) in _ANOS_URNA and uf:
            if int(t["cd_cargo"]) == 12:
                chapa = _sq_prefeito_chapa(
                    conn, int(t["ano"]), uf, t.get("cd_municipio_tse"), t.get("sg_partido")
                )
                if chapa:
                    sq_p, nm_p = chapa
                    res = _resultado_urna(
                        conn,
                        ano=int(t["ano"]),
                        cd_cargo=11,
                        uf=uf,
                        sq=sq_p,
                        cd_municipio_tse=t.get("cd_municipio_tse"),
                    )
                    res["nota_chapa"] = nm_p
                    item["resultado"] = res
                    item["via_chapa"] = True
                else:
                    item["resultado"] = None
                    item["via_chapa"] = True
                    item["chapa_nao_resolvida"] = True
            else:
                item["resultado"] = _resultado_urna(
                    conn,
                    ano=int(t["ano"]),
                    cd_cargo=int(t["cd_cargo"]),
                    uf=uf,
                    sq=int(t["sq_candidato"]),
                    cd_municipio_tse=t.get("cd_municipio_tse"),
                )
                item["via_chapa"] = False
        else:
            item["resultado"] = None
            item["via_chapa"] = False
        historico.append(item)

    # --- texto narrativo ---
    uf_txt = uf or "Brasil"
    linhas = [
        f"Trajetória — {nome} ({partido_atual}).",
        "Sujeito: candidato do escopo da campanha. Fonte: candidatura + urna TSE (Trilha A).",
        "",
    ]

    # presente
    linhas.append(
        f"Concorrendo a {cargo_atual} pelo partido {partido_atual} "
        f"no {'estado do ' + uf_txt if uf else 'Brasil'} ({ano_ref})"
        + ("; resultado de urna ainda inexistente neste recorte." if ano_ref >= 2026 else ".")
    )

    passadas = [h for h in historico if int(h["ano"]) < ano_ref]
    # também inclui mesmo ano se cargo diferente? só < ano_ref
    if not passadas:
        linhas += [
            "",
            f"Sem histórico de outros mandatos ou candidaturas na base oficial deste recorte "
            f"(2014–2024) para {nome} em {uf_txt}.",
        ]
    else:
        linhas.append("")
        linhas.append("Histórico na base oficial:")
        for h in passadas:
            ano = int(h["ano"])
            cargo = h.get("cargo") or ""
            part = h.get("sg_partido") or "—"
            mun = h.get("municipio")
            res = h.get("resultado") or {}
            loc = f" de {mun}" if mun and int(h["cd_cargo"]) in (11, 12, 13) else ""
            estado = f" no estado do {h.get('sg_uf') or uf_txt}"

            if res and res.get("eleito"):
                if int(h["cd_cargo"]) == 12 or h.get("via_chapa"):
                    linhas.append(
                        f"- {ano}: foi vice-prefeito{loc}{estado} pelo partido {part}"
                        + (
                            f" na chapa de {res.get('nota_chapa')}"
                            if res.get("nota_chapa")
                            else ""
                        )
                        + f" — chapa eleita ({_fmt(int(res.get('votos') or 0))} votos)."
                    )
                else:
                    linhas.append(
                        f"- {ano}: foi eleito(a) {cargo}{loc}{estado} pelo partido {part} "
                        f"({_fmt(int(res.get('votos') or 0))} votos)."
                    )
            elif h.get("chapa_nao_resolvida"):
                linhas.append(
                    f"- {ano}: registrado(a) como vice-prefeito{loc}{estado} pelo partido {part}; "
                    f"resultado da chapa não cruzado (prefeito do mesmo partido inexistente no município "
                    f"neste filtro — sem chute)."
                )
            elif res and (res.get("votos") or 0) > 0:
                venc = res.get("vencedor") or {}
                if int(h["cd_cargo"]) == 12 or h.get("via_chapa"):
                    base = (
                        f"- {ano}: concorreu a vice-prefeito{loc}{estado} pelo partido {part}"
                        + (
                            f" na chapa de {res.get('nota_chapa')}"
                            if res.get("nota_chapa")
                            else ""
                        )
                    )
                else:
                    base = f"- {ano}: concorreu a {cargo}{loc}{estado} pelo partido {part}"
                if venc.get("nome"):
                    linhas.append(
                        f"{base}, mas foi derrotado(a) por {venc['nome']} "
                        f"({venc.get('partido') or '—'}) por {_fmt(int(venc.get('margem') or 0))} votos "
                        f"(placar {_fmt(int(venc.get('votos') or 0))} a {_fmt(int(res.get('votos') or 0))})."
                    )
                else:
                    sit = res.get("situacao") or "não eleito"
                    linhas.append(
                        f"{base} — {sit} ({_fmt(int(res.get('votos') or 0))} votos)."
                    )
            else:
                # sem urna encontrada
                linhas.append(
                    f"- {ano}: registrado(a) como candidato(a) a {cargo}{loc}{estado} "
                    f"pelo partido {part}"
                    + (
                        f" (situação cadastral: {h.get('ds_situacao')})"
                        if h.get("ds_situacao")
                        else ""
                    )
                    + "; resultado de urna inexistente ou não cruzado neste filtro."
                )

    return {
        "titulo": f"Trajetória — {nome}",
        "corpo": "\n".join(linhas),
        "fonte": "eleicao.candidatura + eleicao.votacao",
        "nivel": "fato",
        "meta": {
            "contrato": "trajetoria_v2",
            "candidato": nome,
            "n_registros": len(historico),
            "n_passados": len(passadas),
        },
        "registros": historico,
    }
