"""Motor Base de Verdade — cruzamentos oficiais inteligentes → blocos + Perfil."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import psycopg

from gestao import memoria
from gestao.perfil_eleitor import montar_perfil_eleitor
from gestao.store import CARGOS, get_status

_MOTOR_TIPOS = [
    "perfil_eleitor",
    "base_trajetoria",
    "base_concorrentes",
    "base_votos",
    "base_mapa_cargo",
    "base_prefeitos",
    "base_ficha_uf",
    "base_redes",
    "base_eleitorado",
]

# Anos com urna oficial no recorte (nunca 2026 para resultado).
_ANOS_URNA = (2024, 2022, 2020, 2018, 2016, 2014)

# Última urna do cargo (para mapa do pleito, não do candidato).
_URNA_DO_CARGO = {
    1: 2022,  # presidente
    3: 2022,  # governador
    5: 2022,  # senador
    6: 2022,  # dep. federal
    7: 2022,  # dep. estadual
    11: 2024,  # prefeito
    12: 2024,  # vice-prefeito (chapa)
    13: 2024,  # vereador
}


def _cargo_label(cd: int | None) -> str:
    return next((c["label"] for c in CARGOS if c["cd_cargo"] == cd), str(cd or ""))


def _handle_ig(url: str) -> str | None:
    low = (url or "").lower()
    if "instagram.com" not in low:
        return None
    try:
        path = urlparse(url if "://" in url else "https://" + url).path.strip("/")
    except Exception:
        return None
    parts = [p for p in path.split("/") if p and p not in ("p", "reel", "tv")]
    if not parts:
        return None
    return parts[0].lstrip("@").split("?")[0]


def _tokens_nome(nome: str) -> list[str]:
    stop = {"de", "da", "do", "das", "dos", "e"}
    return [t for t in re.split(r"\s+", (nome or "").upper()) if len(t) > 2 and t.lower() not in stop]


def _safe(label: str, conn: psycopg.Connection, fn, fallback, avisos: list[str]):
    try:
        with conn.transaction():
            return fn()
    except Exception as exc:
        avisos.append(f"{label}: {exc}")
        return fallback


def _trajetoria(conn: psycopg.Connection, nm: str, uf: str | None) -> list[dict[str, Any]]:
    tokens = _tokens_nome(nm)
    if len(tokens) < 1:
        return []
    like = "%" + "%".join(tokens[:3]) + "%"
    params: list[Any] = [like, like]
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
        WHERE (c.nm_candidato ILIKE %s OR c.nm_urna ILIKE %s)
          {uf_sql}
          AND c.ano IN (2014, 2016, 2018, 2020, 2022, 2024, 2026)
        ORDER BY c.ano DESC, c.cd_cargo
        LIMIT 40
        """,
        params,
    ).fetchall()
    return [
        {
            "ano": r[0],
            "cd_cargo": r[1],
            "cargo": r[2],
            "sg_uf": r[3],
            "nm_urna": r[4],
            "nm_candidato": r[5],
            "sg_partido": r[6],
            "ds_situacao": r[7],
            "sq_candidato": r[8],
            "nr_candidato": r[9],
            "cd_municipio_tse": r[10],
        }
        for r in rows
    ]


def _concorrentes(
    conn: psycopg.Connection, ano: int, cd_cargo: int, uf: str | None, excluir_sq: int | None
) -> list[dict[str, Any]]:
    params: list[Any] = [ano, cd_cargo]
    uf_sql = ""
    if uf and cd_cargo != 1:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)
    excl = ""
    if excluir_sq:
        excl = " AND c.sq_candidato <> %s"
        params.append(excluir_sq)
    params.append(80)
    rows = conn.execute(
        f"""
        SELECT c.nm_urna, c.nm_candidato, c.sg_partido, c.nr_candidato, c.ds_situacao, c.sq_candidato
        FROM eleicao.candidatura c
        WHERE c.ano = %s AND c.cd_cargo = %s
          {uf_sql}
          {excl}
        ORDER BY c.nm_urna
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [
        {
            "nm_urna": r[0],
            "nm_candidato": r[1],
            "sg_partido": r[2],
            "nr_candidato": r[3],
            "ds_situacao": r[4],
            "sq_candidato": r[5],
        }
        for r in rows
    ]


def _votos_mun(
    conn: psycopg.Connection, ano: int, cd_cargo: int, uf: str, sq: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT COALESCE(m.nome, x.cd_municipio_tse::text) AS mun,
               x.votos
        FROM (
          SELECT v.cd_municipio_tse, SUM(v.qt_votos)::bigint AS votos
          FROM eleicao.votacao v
          WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s
            AND v.sq_candidato = %s AND v.nr_turno = 1
            AND v.cd_municipio_tse IS NOT NULL
          GROUP BY v.cd_municipio_tse
          ORDER BY SUM(v.qt_votos) DESC NULLS LAST
          LIMIT 15
        ) x
        LEFT JOIN ref.municipio m ON m.cd_municipio_tse = x.cd_municipio_tse
        """,
        (ano, cd_cargo, uf, sq),
    ).fetchall()
    return [{"municipio": r[0], "votos": int(r[1] or 0)} for r in rows]


def _sq_prefeito_chapa(
    conn: psycopg.Connection, ano: int, uf: str, cd_municipio_tse: int | None, partido: str | None
) -> tuple[int, str] | None:
    """Vice não tem linha própria de votos nominais — usa a chapa (prefeito) do município."""
    if not cd_municipio_tse:
        return None
    params: list[Any] = [ano, uf, cd_municipio_tse]
    part_sql = ""
    if partido:
        part_sql = " AND upper(c.sg_partido) = upper(%s)"
        params.append(partido)
    row = conn.execute(
        f"""
        SELECT c.sq_candidato, c.nm_urna
        FROM eleicao.candidatura c
        WHERE c.ano = %s AND c.sg_uf = %s AND c.cd_municipio_tse = %s
          AND c.cd_cargo = 11
          {part_sql}
        ORDER BY c.sq_candidato
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row:
        return int(row[0]), row[1] or ""
    # fallback: qualquer prefeito do município naquele ano (lista curta)
    row2 = conn.execute(
        """
        SELECT c.sq_candidato, c.nm_urna
        FROM eleicao.candidatura c
        WHERE c.ano = %s AND c.sg_uf = %s AND c.cd_municipio_tse = %s AND c.cd_cargo = 11
        ORDER BY c.sq_candidato
        LIMIT 1
        """,
        (ano, uf, cd_municipio_tse),
    ).fetchone()
    if row2:
        return int(row2[0]), row2[1] or ""
    return None


def _urna_do_candidato(
    conn: psycopg.Connection,
    traj: list[dict[str, Any]],
    cd_cargo_alvo: int,
    uf: str | None,
) -> dict[str, Any]:
    """
    Busca votos oficiais do candidato em anos anteriores.
    Prioridade: mesmo cargo → cargos majoritários → qualquer urna do recorte.
    Vice-prefeito (12) → votos da chapa de prefeito no município.
    """
    if not uf:
        return {"votos": [], "meta": {}}

    urna = [t for t in traj if int(t["ano"]) in _ANOS_URNA and t.get("sq_candidato")]

    def score(t: dict[str, Any]) -> tuple[int, int]:
        same = 0 if int(t["cd_cargo"]) == cd_cargo_alvo else 1
        # majoritário federal/municipal perto do alvo
        maj = 0 if int(t["cd_cargo"]) in (1, 3, 11, 12) else 2
        return (same, maj, -int(t["ano"]))

    urna.sort(key=score)

    for t in urna:
        ano = int(t["ano"])
        cargo = int(t["cd_cargo"])
        sq = int(t["sq_candidato"])
        label = t.get("cargo") or _cargo_label(cargo)
        nota = f"urna {ano} · {label} · {t.get('nm_urna')}"

        if cargo == 12:
            chapa = _sq_prefeito_chapa(
                conn, ano, uf, t.get("cd_municipio_tse"), t.get("sg_partido")
            )
            if not chapa:
                continue
            sq_p, nm_p = chapa
            votos = _votos_mun(conn, ano, 11, uf, sq_p)
            if votos:
                return {
                    "votos": votos,
                    "meta": {
                        "ano": ano,
                        "cd_cargo": 11,
                        "sq": sq_p,
                        "nota": (
                            f"{nota} — votos nominais da chapa (prefeito {nm_p}); "
                            "vice não figura como linha própria na votação TSE"
                        ),
                        "origem": "chapa_vice",
                    },
                }
            continue

        votos = _votos_mun(conn, ano, cargo, uf, sq)
        if votos:
            return {
                "votos": votos,
                "meta": {
                    "ano": ano,
                    "cd_cargo": cargo,
                    "sq": sq,
                    "nota": nota,
                    "origem": "candidato",
                },
            }
    return {"votos": [], "meta": {}}


def _mapa_cargo_uf(
    conn: psycopg.Connection, cd_cargo: int, uf: str
) -> dict[str, Any]:
    """Mapa da última urna do cargo na UF — votos do(s) eleito(s) por município."""
    ano = _URNA_DO_CARGO.get(cd_cargo)
    cargo_mapa = cd_cargo
    if cd_cargo == 12:
        ano, cargo_mapa = 2024, 11
    if not ano:
        return {"ano": None, "cd_cargo": cd_cargo, "linhas": []}

    if cargo_mapa in (1, 3):
        # Majoritário estadual/federal: um eleito na UF — força por município
        rows = conn.execute(
            """
            SELECT COALESCE(m.nome, v.cd_municipio_tse::text),
                   SUM(v.qt_votos)::bigint,
                   MAX(v.nm_urna),
                   MAX(v.sg_partido)
            FROM eleicao.votacao v
            LEFT JOIN ref.municipio m ON m.cd_municipio_tse = v.cd_municipio_tse
            WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s
              AND v.nr_turno = 1
              AND api._eh_eleito(v.ds_sit_tot_turno)
              AND v.cd_municipio_tse IS NOT NULL
            GROUP BY v.cd_municipio_tse, m.nome
            ORDER BY SUM(v.qt_votos) DESC NULLS LAST
            LIMIT 40
            """,
            (ano, cargo_mapa, uf),
        ).fetchall()
    elif cargo_mapa == 11:
        # Prefeitos: um eleito por município
        rows = conn.execute(
            """
            SELECT COALESCE(m.nome, e.cd_municipio_tse::text),
                   e.qt_votos, e.nm_urna, e.sg_partido
            FROM (
              SELECT a.sq_candidato, a.nm_urna, a.sg_partido, a.qt_votos, c.cd_municipio_tse
              FROM (
                SELECT v.sq_candidato,
                       MAX(v.nm_urna) AS nm_urna,
                       MAX(v.sg_partido) AS sg_partido,
                       SUM(v.qt_votos)::bigint AS qt_votos
                FROM eleicao.votacao v
                WHERE v.ano = %s AND v.cd_cargo = 11 AND v.sg_uf = %s
                  AND api._eh_eleito(v.ds_sit_tot_turno)
                GROUP BY v.sq_candidato
              ) a
              LEFT JOIN eleicao.candidatura c
                ON c.ano = %s AND c.sq_candidato = a.sq_candidato
            ) e
            LEFT JOIN ref.municipio m ON m.cd_municipio_tse = e.cd_municipio_tse
            ORDER BY e.qt_votos DESC NULLS LAST
            LIMIT 40
            """,
            (ano, uf, ano),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT COALESCE(m.nome, x.cd_municipio_tse::text), x.votos, x.nm_urna, x.sg_partido
            FROM (
              SELECT v.cd_municipio_tse,
                     SUM(v.qt_votos)::bigint AS votos,
                     MAX(v.nm_urna) AS nm_urna,
                     MAX(v.sg_partido) AS sg_partido
              FROM eleicao.votacao v
              WHERE v.ano = %s AND v.cd_cargo = %s AND v.sg_uf = %s AND v.nr_turno = 1
                AND api._eh_eleito(v.ds_sit_tot_turno)
                AND v.cd_municipio_tse IS NOT NULL
              GROUP BY v.cd_municipio_tse
              ORDER BY SUM(v.qt_votos) DESC NULLS LAST
              LIMIT 20
            ) x
            LEFT JOIN ref.municipio m ON m.cd_municipio_tse = x.cd_municipio_tse
            """,
            (ano, cargo_mapa, uf),
        ).fetchall()

    return {
        "ano": ano,
        "cd_cargo": cargo_mapa,
        "linhas": [
            {
                "municipio": r[0],
                "votos": int(r[1] or 0),
                "eleito": r[2],
                "partido": r[3],
            }
            for r in rows
            if r[0]
        ],
    }


def _prefeitos(conn: psycopg.Connection, uf: str, partido: str | None) -> dict[str, Any]:
    """Prefeitos eleitos 2024 = urna (ds_sit_tot_turno), nunca ds_situacao de candidatura."""
    rows = conn.execute(
        """
        SELECT COALESCE(m.nome, e.cd_municipio_tse::text),
               e.nm_urna, e.sg_partido, e.ds_sit_tot_turno, e.qt_votos
        FROM (
          SELECT DISTINCT ON (a.sq_candidato)
            a.sq_candidato, a.nm_urna, a.sg_partido, a.ds_sit_tot_turno, a.qt_votos,
            c.cd_municipio_tse
          FROM (
            SELECT v.sq_candidato,
                   MAX(v.nm_urna) AS nm_urna,
                   MAX(v.sg_partido) AS sg_partido,
                   MAX(v.ds_sit_tot_turno) AS ds_sit_tot_turno,
                   SUM(v.qt_votos)::bigint AS qt_votos
            FROM eleicao.votacao v
            WHERE v.ano = 2024 AND v.cd_cargo = 11 AND v.sg_uf = %s
              AND api._eh_eleito(v.ds_sit_tot_turno)
            GROUP BY v.sq_candidato
          ) a
          LEFT JOIN eleicao.candidatura c
            ON c.ano = 2024 AND c.sq_candidato = a.sq_candidato
          ORDER BY a.sq_candidato
        ) e
        LEFT JOIN ref.municipio m ON m.cd_municipio_tse = e.cd_municipio_tse
        ORDER BY m.nome NULLS LAST
        LIMIT 80
        """,
        (uf,),
    ).fetchall()
    aliados = []
    outros = []
    part = (partido or "").upper()
    for r in rows:
        item = {
            "municipio": r[0],
            "prefeito": r[1],
            "partido": r[2],
            "situacao": r[3],
            "votos": int(r[4] or 0),
        }
        if part and (r[2] or "").upper() == part:
            aliados.append(item)
        else:
            outros.append(item)
    return {
        "aliados_partido": aliados,
        "outros": outros,
        "total_eleitos": len(rows),
        "fonte": "eleicao.votacao 2024 cargo 11 + api._eh_eleito",
    }


def _fichas_uf(conn: psycopg.Connection, uf: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.ano_eleicao, d.titulo,
               string_agg(c.texto, E'\n' ORDER BY c.ord)
        FROM acervo.documento d
        JOIN acervo.chunk c ON c.documento_id = d.id
        WHERE d.ativo IS TRUE
          AND d.tipo = 'ficha_territorial'
          AND d.sg_uf = %s
          AND d.ano_eleicao IN (2024, 2022, 2020, 2018)
        GROUP BY d.id, d.ano_eleicao, d.titulo
        ORDER BY d.ano_eleicao DESC
        LIMIT 4
        """,
        (uf,),
    ).fetchall()
    return [
        {"ano": int(r[0]), "titulo": r[1] or "", "corpo": (r[2] or "").strip()}
        for r in rows
        if r[2]
    ]


def _redes(conn: psycopg.Connection, ano: int, sq: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ds_url, nr_ordem
        FROM eleicao.rede_social
        WHERE ano = %s AND sq_candidato = %s
        ORDER BY nr_ordem NULLS LAST, ds_url
        LIMIT 30
        """,
        (ano, sq),
    ).fetchall()
    out = []
    for r in rows:
        url = r[0] or ""
        out.append({"url": url, "handle_ig": _handle_ig(url), "ordem": r[1]})
    return out


def _redes_traj(conn: psycopg.Connection, traj: list[dict[str, Any]], ano_ref: int, sq_ref: int) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    keys: set[str] = set()
    for ano, sq in [(ano_ref, sq_ref)] + [
        (int(t["ano"]), int(t["sq_candidato"]))
        for t in traj
        if t.get("sq_candidato") and int(t["ano"]) <= ano_ref
    ]:
        for r in _redes(conn, ano, sq):
            k = (r.get("url") or "").lower()
            if not k or k in keys:
                continue
            keys.add(k)
            seen.append(r)
    return seen[:30]


def _eleitorado(conn: psycopg.Connection, uf: str) -> dict[str, Any]:
    out: dict[str, Any] = {"municipios": 0}
    mun = conn.execute(
        "SELECT COUNT(*)::int FROM ref.municipio WHERE sg_uf = %s",
        (uf,),
    ).fetchone()
    out["municipios"] = int(mun[0] or 0) if mun else 0
    for ano in (2026, 2024, 2022):
        row = conn.execute(
            """
            SELECT COALESCE(SUM(qt_eleitores)::bigint, 0)
            FROM eleicao.eleitorado
            WHERE ano = %s AND sg_uf = %s
            """,
            (ano, uf),
        ).fetchone()
        out[f"eleitores_{ano}"] = int(row[0] or 0) if row else 0
    return out


def rodar_motor(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    if not st.get("sq_candidato") or not st.get("cd_cargo") or not st.get("ano_ref"):
        raise ValueError("Escopo incompleto — salve ano, cargo, UF e candidato antes do motor")

    try:
        conn.execute("SET LOCAL statement_timeout = '60000'")
    except Exception:
        pass

    ano = int(st["ano_ref"])
    cd = int(st["cd_cargo"])
    uf = st.get("sg_uf")
    sq = int(st["sq_candidato"])
    nm = st.get("nm_candidato") or st.get("nm_urna") or ""
    avisos: list[str] = []

    traj = _safe("trajetoria", conn, lambda: _trajetoria(conn, nm, uf if cd != 1 else None), [], avisos)
    conc = _safe("concorrentes", conn, lambda: _concorrentes(conn, ano, cd, uf, sq), [], avisos)

    urna_cand = _safe(
        "votos_candidato",
        conn,
        lambda: _urna_do_candidato(conn, traj, cd, uf),
        {"votos": [], "meta": {}},
        avisos,
    )
    votos = urna_cand.get("votos") or []
    meta_votos = urna_cand.get("meta") or {}

    mapa = (
        _safe("mapa_cargo", conn, lambda: _mapa_cargo_uf(conn, cd, uf), {"ano": None, "linhas": []}, avisos)
        if uf
        else {"ano": None, "linhas": []}
    )
    pref = (
        _safe(
            "prefeitos",
            conn,
            lambda: _prefeitos(conn, uf, st.get("sg_partido")),
            {"aliados_partido": [], "outros": [], "total_eleitos": 0},
            avisos,
        )
        if uf
        else {"aliados_partido": [], "outros": [], "total_eleitos": 0}
    )
    fichas = _safe("fichas", conn, lambda: _fichas_uf(conn, uf), [], avisos) if uf else []
    redes = _safe("redes", conn, lambda: _redes_traj(conn, traj, ano, sq), [], avisos)
    elei = (
        _safe(
            "eleitorado",
            conn,
            lambda: _eleitorado(conn, uf),
            {"eleitores_2026": 0, "eleitores_2024": 0, "eleitores_2022": 0, "municipios": 0},
            avisos,
        )
        if uf
        else {"eleitores_2026": 0, "eleitores_2024": 0, "eleitores_2022": 0, "municipios": 0}
    )

    memoria.limpar_tipos(conn, campanha_id, _MOTOR_TIPOS)

    corp_tr = "Trajetória eleitoral (candidaturas na base oficial):\n"
    if traj:
        for t in traj:
            corp_tr += (
                f"- {t['ano']} · {t['cargo']} · {t['sg_uf']} · {t['nm_urna']} · "
                f"{t['sg_partido']} · {t['ds_situacao']}\n"
            )
    else:
        corp_tr += "Inexistente cruzamento por nome na base deste recorte.\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_trajetoria",
        titulo=f"Trajetória — {st.get('nm_urna') or nm}",
        corpo=corp_tr,
        fonte="eleicao.candidatura",
        nivel="fato",
        meta={"n": len(traj)},
    )

    corp_c = f"Concorrentes {ano} · {_cargo_label(cd)} · {uf or 'BR'}:\n"
    for c in conc[:50]:
        corp_c += f"- {c['nm_urna']} · {c['sg_partido']} · nº {c['nr_candidato']} · {c['ds_situacao']}\n"
    if not conc:
        corp_c += "Lista vazia neste filtro.\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_concorrentes",
        titulo="Concorrentes do cargo",
        corpo=corp_c,
        fonte="eleicao.candidatura",
        nivel="fato",
        meta={"n": len(conc)},
    )

    corp_v = "Geografia do voto do candidato (urna anterior):\n"
    if meta_votos.get("nota"):
        corp_v += f"Fonte: {meta_votos['nota']}\n"
    if votos:
        for v in votos:
            corp_v += f"- {v['municipio']}: {v['votos']:,} votos\n".replace(",", ".")
    else:
        corp_v += (
            "Inexistente votos nominais do próprio candidato em anos anteriores "
            "(use mapa do cargo + prefeitos + fichas).\n"
        )
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_votos",
        titulo="Geografia do voto (candidato)",
        corpo=corp_v,
        fonte="eleicao.votacao",
        nivel="fato",
        meta=meta_votos,
    )

    corp_m = (
        f"Mapa do cargo na UF — última urna "
        f"({_cargo_label(mapa.get('cd_cargo') or cd)} · {mapa.get('ano') or '—'}):\n"
    )
    if mapa.get("linhas"):
        for ln in mapa["linhas"][:30]:
            corp_m += (
                f"- {ln['municipio']}: {ln['eleito']} ({ln['partido']}) — "
                f"{ln['votos']:,} votos\n".replace(",", ".")
            )
    else:
        corp_m += "Inexistente neste filtro.\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_mapa_cargo",
        titulo="Mapa do cargo (última urna da UF)",
        corpo=corp_m,
        fonte="eleicao.votacao + api._eh_eleito",
        nivel="fato",
        meta={"ano": mapa.get("ano"), "n": len(mapa.get("linhas") or [])},
    )

    corp_p = "Prefeitos eleitos 2024 na UF (situação de urna, não cadastro):\n"
    if pref.get("total_eleitos"):
        corp_p += f"Total: {pref['total_eleitos']}. Mesmo partido do candidato: {len(pref.get('aliados_partido') or [])}.\n"
        for a in (pref.get("aliados_partido") or []):
            corp_p += f"- ALIADO partidário: {a['municipio']} — {a['prefeito']} ({a['partido']})\n"
        for a in (pref.get("outros") or []):
            corp_p += f"- {a['municipio']} — {a['prefeito']} ({a['partido']})\n"
    else:
        corp_p += "Inexistente ou UF ausente.\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_prefeitos",
        titulo="Mapa de prefeitos 2024",
        corpo=corp_p,
        fonte="eleicao.votacao 2024 + api._eh_eleito",
        nivel="fato",
        meta={"total_eleitos": pref.get("total_eleitos"), "aliados": len(pref.get("aliados_partido") or [])},
    )

    if fichas:
        for i, f in enumerate(fichas):
            memoria.upsert_bloco(
                conn, campanha_id,
                tipo="base_ficha_uf",
                titulo=f.get("titulo") or f"Ficha territorial {uf} · {f.get('ano')}",
                corpo=f.get("corpo") or "",
                fonte="acervo.ficha_territorial (derivado Trilha A)",
                nivel="indicio",
                meta={"ano": f.get("ano"), "i": i},
            )
    else:
        memoria.upsert_bloco(
            conn, campanha_id,
            tipo="base_ficha_uf",
            titulo=f"Ficha territorial {uf or '—'}",
            corpo="Inexistente ficha territorial no Acervo para esta UF nos anos 2018–2024.",
            fonte="acervo",
            nivel="indicio",
            meta={},
        )

    corp_r = "Redes TSE do candidato (ano do escopo + trajetória):\n"
    if redes:
        for r in redes:
            corp_r += f"- {r['url']}" + (f" (IG @{r['handle_ig']})" if r.get("handle_ig") else "") + "\n"
    else:
        corp_r += "Inexistente na base (pacote rede_social pode estar vazio em 2026).\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_redes",
        titulo="Redes sociais TSE",
        corpo=corp_r,
        fonte="eleicao.rede_social",
        nivel="fato",
        meta={"n": len(redes), "ig": [r["handle_ig"] for r in redes if r.get("handle_ig")]},
    )

    corp_e = (
        f"Eleitorado {uf or '—'}:\n"
        f"- 2026: {elei.get('eleitores_2026') or 'inexistente'}\n"
        f"- 2024: {elei.get('eleitores_2024') or 'inexistente'}\n"
        f"- 2022: {elei.get('eleitores_2022') or 'inexistente'}\n"
        f"- Municípios: {elei.get('municipios') or '—'}\n"
    )
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_eleitorado",
        titulo="Eleitorado da UF",
        corpo=corp_e,
        fonte="eleicao.eleitorado",
        nivel="fato",
        meta=elei,
    )

    perfil_doc = _safe(
        "perfil_eleitor",
        conn,
        lambda: montar_perfil_eleitor(
            conn,
            uf=uf or "",
            cd_cargo=cd,
            cargo_label=st.get("cargo_label") or _cargo_label(cd),
        ),
        None,
        avisos,
    )
    if perfil_doc:
        memoria.upsert_bloco(
            conn, campanha_id,
            tipo="perfil_eleitor",
            titulo=perfil_doc["titulo"],
            corpo=perfil_doc["corpo"],
            fonte=perfil_doc["fonte"],
            nivel=perfil_doc.get("nivel") or "fato",
            meta=perfil_doc.get("meta") or {"motor": "perfil_v2"},
        )
    else:
        memoria.upsert_bloco(
            conn, campanha_id,
            tipo="perfil_eleitor",
            titulo=f"Perfil eleitoral — {uf or '—'}",
            corpo="Perfil eleitoral indisponível (UF ausente ou falha no motor). Sem estimativa.",
            fonte="motor Gestão",
            nivel="fato",
            meta={"motor": "perfil_v2", "ok": False},
        )

    try:
        conn.execute(
            """
            INSERT INTO ctl.radar_config (campanha_id, candidato_nome, uf, cargo, atualizado_em)
            VALUES (%s::uuid, %s, %s, %s, now())
            ON CONFLICT (campanha_id) DO UPDATE SET
              candidato_nome = EXCLUDED.candidato_nome,
              uf = EXCLUDED.uf,
              cargo = EXCLUDED.cargo,
              atualizado_em = now()
            """,
            (campanha_id, st.get("nm_urna") or nm, uf, _cargo_label(cd)),
        )
    except Exception:
        pass

    return {
        "ok": True,
        "blocos": len(_MOTOR_TIPOS),
        "trajetoria": len(traj),
        "concorrentes": len(conc),
        "votos_mun": len(votos),
        "prefeitos": pref.get("total_eleitos") or 0,
        "mapa_cargo": len(mapa.get("linhas") or []),
        "fichas": len(fichas),
        "redes": len(redes),
        "tem_perfil": bool(perfil_doc),
        "perfil_meta": (perfil_doc or {}).get("meta"),
        "avisos": avisos,
        "status": get_status(conn, campanha_id),
    }
