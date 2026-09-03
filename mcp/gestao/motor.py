"""Motor Base de Verdade — snapshot oficial → blocos + Perfil de Eleitor."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import psycopg

from gestao import memoria
from gestao.store import CARGOS, get_status

_MOTOR_TIPOS = [
    "perfil_eleitor",
    "base_trajetoria",
    "base_concorrentes",
    "base_votos",
    "base_prefeitos",
    "base_redes",
    "base_eleitorado",
]

_CARGO_ANO_URNA = {
    1: [2022, 2018],
    3: [2022, 2018],
    5: [2022, 2018],
    6: [2022, 2018],
    7: [2022, 2018],
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


def _trajetoria(conn: psycopg.Connection, nm: str, uf: str | None) -> list[dict[str, Any]]:
    tokens = _tokens_nome(nm)
    if len(tokens) < 1:
        return []
    # exige pelo menos 2 tokens se houver; senão 1
    like = "%" + "%".join(tokens[:3]) + "%"
    params: list[Any] = [like, like]
    uf_sql = ""
    if uf:
        uf_sql = " AND c.sg_uf = %s"
        params.append(uf)
    rows = conn.execute(
        f"""
        SELECT c.ano, c.cd_cargo, r.nome AS cargo, c.sg_uf, c.nm_urna, c.nm_candidato,
               c.sg_partido, c.ds_situacao, c.sq_candidato, c.nr_candidato
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
    params.append(40)
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
    # Agrega por município antes do ORDER — evita scan ordenado pesado em votacao.
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


def _melhor_sq_historico(
    traj: list[dict[str, Any]], cd_cargo: int, uf: str | None
) -> tuple[int, int] | None:
    anos = _CARGO_ANO_URNA.get(cd_cargo) or [2022]
    for ano in anos:
        for t in traj:
            if t["ano"] == ano and t["cd_cargo"] == cd_cargo:
                if uf and t.get("sg_uf") and t["sg_uf"] != uf and cd_cargo != 1:
                    continue
                return ano, int(t["sq_candidato"])
    for ano in anos:
        for t in traj:
            if t["ano"] == ano:
                return ano, int(t["sq_candidato"])
    return None


def _prefeitos(conn: psycopg.Connection, uf: str, partido: str | None) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT COALESCE(m.nome, c.cd_municipio_tse::text),
               c.nm_urna, c.sg_partido, c.ds_situacao
        FROM eleicao.candidatura c
        LEFT JOIN ref.municipio m ON m.cd_municipio_tse = c.cd_municipio_tse
        WHERE c.ano = 2024 AND c.cd_cargo = 11 AND c.sg_uf = %s
          AND c.ds_situacao ILIKE '%%ELEITO%%'
        ORDER BY m.nome NULLS LAST
        LIMIT 80
        """,
        (uf,),
    ).fetchall()
    aliados = []
    outros = []
    part = (partido or "").upper()
    for r in rows:
        item = {"municipio": r[0], "prefeito": r[1], "partido": r[2], "situacao": r[3]}
        if part and (r[2] or "").upper() == part:
            aliados.append(item)
        else:
            outros.append(item)
    return {"aliados_partido": aliados, "outros": outros[:40], "total_eleitos": len(rows)}


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


def _eleitorado(conn: psycopg.Connection, uf: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(qt_eleitores)::bigint, 0)
        FROM eleicao.eleitorado
        WHERE ano = 2026 AND sg_uf = %s
        """,
        (uf,),
    ).fetchone()
    mun = conn.execute(
        "SELECT COUNT(*)::int FROM ref.municipio WHERE sg_uf = %s",
        (uf,),
    ).fetchone()
    return {
        "eleitores_2026": int(row[0] or 0) if row else 0,
        "municipios": int(mun[0] or 0) if mun else 0,
    }


def _bloco_perfil(
    st: dict[str, Any],
    traj: list[dict[str, Any]],
    votos: list[dict[str, Any]],
    pref: dict[str, Any],
    elei: dict[str, Any],
    conc: list[dict[str, Any]],
) -> str:
    nome = st.get("nm_urna") or st.get("nm_candidato") or "Candidato"
    uf = st.get("sg_uf") or "—"
    cargo = st.get("cargo_label") or _cargo_label(st.get("cd_cargo"))
    linhas = [
        f"Perfil de eleitor — recorte {cargo} · {uf} · campanha de {nome} ({st.get('sg_partido') or 's/partido'}).",
        "",
        "Dimensão territorial:",
        f"- Eleitorado 2026 (UF): {elei.get('eleitores_2026') or 'inexistente na base'}.",
        f"- Municípios na malha: {elei.get('municipios') or '—'}.",
    ]
    if votos:
        top = votos[:5]
        bot = list(reversed(votos[-3:])) if len(votos) >= 3 else []
        linhas.append("- Geografia do voto (última urna encontrada do candidato):")
        linhas.append(
            "  Mais votos: "
            + "; ".join(f"{v['municipio']} ({v['votos']:,})".replace(",", ".") for v in top)
        )
        if bot:
            linhas.append(
                "  Menor presença entre o top listado: "
                + "; ".join(f"{v['municipio']} ({v['votos']:,})".replace(",", ".") for v in bot)
            )
    else:
        linhas.append(
            "- Geografia do voto: inexistente para cruzamento automático "
            "(sem urna anterior compatível na base)."
        )
    if pref.get("total_eleitos"):
        n_al = len(pref.get("aliados_partido") or [])
        linhas.append(
            f"- Prefeitos eleitos 2024 na UF: {pref['total_eleitos']}; "
            f"do mesmo partido do candidato ({st.get('sg_partido') or '—'}): {n_al}."
        )
        if pref.get("aliados_partido"):
            amostra = pref["aliados_partido"][:8]
            linhas.append(
                "  Amostra aliados partidários: "
                + "; ".join(f"{a['municipio']} ({a['prefeito']})" for a in amostra)
            )
    linhas += [
        "",
        "Densidade política:",
        f"- Concorrentes registrados 2026 no mesmo cargo/UF (exc. o próprio): {len(conc)}.",
        f"- Trajetória candidaturas encontradas na base: {len(traj)} registros.",
        "",
        "Leitura operacional (hipótese ancorada — validar com dossiê/campanha):",
        "- Use este perfil para priorizar território, contrastar com clima (Radar) e amarrar pautas do plano.",
        "- Cifras citadas acima são Trilha A; interpretações são indício até a coordenação validar.",
    ]
    return "\n".join(linhas)


def _safe(label: str, conn: psycopg.Connection, fn, fallback, avisos: list[str]):
    try:
        with conn.transaction():
            return fn()
    except Exception as exc:
        avisos.append(f"{label}: {exc}")
        return fallback


def rodar_motor(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    if not st.get("sq_candidato") or not st.get("cd_cargo") or not st.get("ano_ref"):
        raise ValueError("Escopo incompleto — salve ano, cargo, UF e candidato antes do motor")

    # Evita derrubar o proxy EasyPanel (HTML "Service is not reachable") em query longa.
    try:
        conn.execute("SET LOCAL statement_timeout = '20000'")
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
    hist = _melhor_sq_historico(traj, cd, uf)
    votos: list[dict[str, Any]] = []
    ano_votos = None
    if hist and uf:
        ano_votos, sq_h = hist

        def _v1():
            return _votos_mun(conn, ano_votos, cd, uf, sq_h)

        votos = _safe("votos", conn, _v1, [], avisos)
        if not votos:
            for t in traj:
                if t["ano"] == ano_votos and t.get("sg_uf") == uf and t.get("sq_candidato"):
                    cargo_h = int(t["cd_cargo"])
                    sq_t = int(t["sq_candidato"])

                    def _v2(c=cargo_h, s=sq_t):
                        return _votos_mun(conn, ano_votos, c, uf, s)

                    votos = _safe("votos_hist", conn, _v2, [], avisos)
                    if votos:
                        break
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
    redes = _safe("redes", conn, lambda: _redes(conn, ano, sq), [], avisos)
    elei = (
        _safe(
            "eleitorado",
            conn,
            lambda: _eleitorado(conn, uf),
            {"eleitores_2026": 0, "municipios": 0},
            avisos,
        )
        if uf
        else {"eleitores_2026": 0, "municipios": 0}
    )

    memoria.limpar_tipos(conn, campanha_id, _MOTOR_TIPOS)

    # trajetória
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
    for c in conc[:35]:
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

    corp_v = "Geografia do voto (última urna compatível):\n"
    if ano_votos and votos:
        corp_v += f"Ano {ano_votos}, turno 1, top municípios:\n"
        for v in votos:
            corp_v += f"- {v['municipio']}: {v['votos']:,} votos\n".replace(",", ".")
    else:
        corp_v += "Inexistente para este candidato/cargo na base (ou sem UF).\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_votos",
        titulo="Geografia do voto",
        corpo=corp_v,
        fonte="eleicao.votacao",
        nivel="fato",
        meta={"ano": ano_votos, "n": len(votos)},
    )

    corp_p = "Prefeitos eleitos 2024 na UF vs partido do candidato:\n"
    if pref.get("total_eleitos"):
        corp_p += f"Total eleitos listados: {pref['total_eleitos']}. Mesmo partido: {len(pref.get('aliados_partido') or [])}.\n"
        for a in (pref.get("aliados_partido") or [])[:25]:
            corp_p += f"- ALIADO partidário: {a['municipio']} — {a['prefeito']} ({a['partido']})\n"
        for a in (pref.get("outros") or [])[:15]:
            corp_p += f"- Outro: {a['municipio']} — {a['prefeito']} ({a['partido']})\n"
    else:
        corp_p += "Inexistente ou UF ausente.\n"
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="base_prefeitos",
        titulo="Mapa de prefeitos 2024",
        corpo=corp_p,
        fonte="eleicao.candidatura 2024 cargo 11",
        nivel="fato",
        meta={"total_eleitos": pref.get("total_eleitos"), "aliados": len(pref.get("aliados_partido") or [])},
    )

    corp_r = "Redes TSE do candidato (ano do escopo):\n"
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
        f"- Eleitores 2026 (soma UF): {elei.get('eleitores_2026') or 'inexistente'}\n"
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

    perfil = _bloco_perfil(st, traj, votos, pref, elei, conc)
    memoria.upsert_bloco(
        conn, campanha_id,
        tipo="perfil_eleitor",
        titulo=f"Perfil de eleitor — {st.get('nm_urna') or nm}",
        corpo=perfil,
        fonte="motor Gestão (TSE/IBGE malha) + síntese",
        nivel="indicio",
        meta={"motor": "s2"},
    )

    # espelha no radar_config
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
        "redes": len(redes),
        "tem_perfil": True,
        "avisos": avisos,
        "status": get_status(conn, campanha_id),
    }
