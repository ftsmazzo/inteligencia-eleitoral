"""Store do módulo Mapa."""
from __future__ import annotations

import json
from typing import Any

import psycopg


def campanha_do_usuario(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT COALESCE(campanha_ativa_id, campanha_id)::text, email
        FROM ctl.apura_usuario
        WHERE id = %s::uuid
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def listar_municipios(conn: psycopg.Connection, uf: str = "AP") -> list[dict[str, Any]]:
    uf = (uf or "AP").strip().upper()[:2]
    rows = conn.execute(
        """
        SELECT g.cod_ibge, g.nome, g.sg_uf, g.lat, g.lng
        FROM ctl.municipio_geo g
        WHERE g.sg_uf = %s
        ORDER BY g.nome
        """,
        (uf,),
    ).fetchall()
    return [
        {
            "cod_ibge": int(r[0]),
            "nome": r[1],
            "sg_uf": r[2],
            "lat": float(r[3]),
            "lng": float(r[4]),
        }
        for r in rows
    ]


def listar_notas(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT n.id::text, n.cod_ibge, COALESCE(g.nome, n.cod_ibge::text), n.texto,
               n.atualizado_em::text, n.atualizado_por::text
        FROM ctl.mapa_nota n
        LEFT JOIN ctl.municipio_geo g ON g.cod_ibge = n.cod_ibge
        WHERE n.campanha_id = %s::uuid
        ORDER BY g.nome NULLS LAST
        """,
        (campanha_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "cod_ibge": int(r[1]),
            "nome": r[2],
            "texto": r[3] or "",
            "atualizado_em": r[4],
            "atualizado_por": r[5],
        }
        for r in rows
    ]


def upsert_nota(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    cod_ibge: int,
    texto: str,
    usuario_id: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO ctl.mapa_nota (campanha_id, cod_ibge, texto, atualizado_por, atualizado_em)
        VALUES (%s::uuid, %s, %s, %s::uuid, now())
        ON CONFLICT (campanha_id, cod_ibge) DO UPDATE SET
          texto = EXCLUDED.texto,
          atualizado_por = EXCLUDED.atualizado_por,
          atualizado_em = now()
        RETURNING id::text, cod_ibge, texto, atualizado_em::text
        """,
        (campanha_id, cod_ibge, (texto or "")[:20000], usuario_id),
    ).fetchone()
    nome_row = conn.execute(
        "SELECT nome FROM ctl.municipio_geo WHERE cod_ibge = %s",
        (cod_ibge,),
    ).fetchone()
    return {
        "id": row[0],
        "cod_ibge": int(row[1]),
        "nome": nome_row[0] if nome_row else str(cod_ibge),
        "texto": row[2] or "",
        "atualizado_em": row[3],
    }


def apagar_nota(conn: psycopg.Connection, *, campanha_id: str, cod_ibge: int) -> bool:
    cur = conn.execute(
        "DELETE FROM ctl.mapa_nota WHERE campanha_id = %s::uuid AND cod_ibge = %s",
        (campanha_id, cod_ibge),
    )
    return (cur.rowcount or 0) > 0


def listar_caravanas(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id::text, nome, pontos_json, rota_geojson, atualizado_em::text
        FROM ctl.mapa_caravana
        WHERE campanha_id = %s::uuid
        ORDER BY atualizado_em DESC
        """,
        (campanha_id,),
    ).fetchall()
    out = []
    for r in rows:
        pontos = r[2]
        if isinstance(pontos, str):
            pontos = json.loads(pontos)
        rota = r[3]
        if isinstance(rota, str):
            rota = json.loads(rota)
        out.append(
            {
                "id": r[0],
                "nome": r[1],
                "pontos": pontos or [],
                "rota_geojson": rota,
                "atualizado_em": r[4],
            }
        )
    return out


def salvar_caravana(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    nome: str,
    pontos: list[dict[str, Any]],
    rota_geojson: Any = None,
    usuario_id: str | None = None,
    caravana_id: str | None = None,
) -> dict[str, Any]:
    pontos_json = json.dumps(pontos or [], ensure_ascii=False)
    rota_json = json.dumps(rota_geojson, ensure_ascii=False) if rota_geojson is not None else None
    if caravana_id:
        row = conn.execute(
            """
            UPDATE ctl.mapa_caravana
            SET nome = %s, pontos_json = %s::jsonb,
                rota_geojson = COALESCE(%s::jsonb, rota_geojson),
                atualizado_em = now()
            WHERE id = %s::uuid AND campanha_id = %s::uuid
            RETURNING id::text, nome, pontos_json, rota_geojson, atualizado_em::text
            """,
            (nome[:200], pontos_json, rota_json, caravana_id, campanha_id),
        ).fetchone()
        if not row:
            raise ValueError("caravana não encontrada")
    else:
        row = conn.execute(
            """
            INSERT INTO ctl.mapa_caravana
              (campanha_id, nome, pontos_json, rota_geojson, criado_por)
            VALUES (%s::uuid, %s, %s::jsonb, %s::jsonb, %s::uuid)
            RETURNING id::text, nome, pontos_json, rota_geojson, atualizado_em::text
            """,
            (campanha_id, nome[:200] or "Carreata", pontos_json, rota_json, usuario_id),
        ).fetchone()
    pontos_out = row[2]
    if isinstance(pontos_out, str):
        pontos_out = json.loads(pontos_out)
    rota_out = row[3]
    if isinstance(rota_out, str):
        rota_out = json.loads(rota_out)
    return {
        "id": row[0],
        "nome": row[1],
        "pontos": pontos_out or [],
        "rota_geojson": rota_out,
        "atualizado_em": row[4],
    }


def apagar_caravana(conn: psycopg.Connection, *, campanha_id: str, caravana_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM ctl.mapa_caravana WHERE id = %s::uuid AND campanha_id = %s::uuid",
        (caravana_id, campanha_id),
    )
    return (cur.rowcount or 0) > 0


# Rótulos TRE-AP (composição territorial — não é polígono). Fonte: portal TRE-AP.
ZONA_AP_COMPOSICAO: dict[int, str] = {
    1: "Amapá, Calçoene e Pracuúba",
    2: "Macapá (Zona Sul)",
    4: "Oiapoque",
    5: "Mazagão",
    6: "Santana",
    7: "Laranjal do Jari e Vitória do Jari",
    8: "Tartarugalzinho",
    10: "Macapá (Zona Norte), Cutias e Itaubal",
    11: "Pedra Branca do Amapari e Serra do Navio",
    12: "Porto Grande e Ferreira Gomes",
    14: "Macapá",
}


def _norm_nome(s: str | None) -> str:
    import re
    import unicodedata

    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^A-Z0-9 ]+", " ", t.upper())
    return " ".join(t.split())


def _nomes_compativeis(a: str | None, b: str | None) -> bool:
    """Exige identidade onomástica — nº de urna sozinho não basta."""
    na, nb = _norm_nome(a), _norm_nome(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # tokens significativos (ignora DE/DA/DO)
    skip = {"DE", "DA", "DO", "DAS", "DOS", "E"}
    ta = {x for x in na.split() if len(x) >= 3 and x not in skip}
    tb = {x for x in nb.split() if len(x) >= 3 and x not in skip}
    if not ta or not tb:
        return False
    # overlap forte: pelo menos 2 tokens ou um nome completo contido
    inter = ta & tb
    if len(inter) >= 2:
        return True
    if na in nb or nb in na:
        return True
    return False


def _resolver_sq_na_urna(
    conn: psycopg.Connection,
    *,
    ano: int,
    uf: str,
    cargo: int,
    turno: int,
    sq_campanha: int,
    nr_candidato: int | None,
    nm_urna: str | None,
    nm_candidato: str | None,
    sg_partido: str | None,
) -> dict[str, Any]:
    """Resolve sq na urna do ano com identidade do candidato.

    Nunca casa só por nr_candidato (nº 16 PSTU ≠ outro nº 16 de outro ano/pessoa).
    Ordem: sq campanha → nm_urna/nm_candidato na votação → candidatura → nr+nome.
    """
    hit = conn.execute(
        """
        SELECT COALESCE(SUM(qt_votos), 0)::bigint, MAX(nm_urna), MAX(sg_partido)
        FROM eleicao.votacao
        WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND nr_turno = %s
          AND sq_candidato = %s
        """,
        (ano, uf, cargo, turno, sq_campanha),
    ).fetchone()
    if hit and int(hit[0] or 0) > 0:
        return {
            "sq_candidato": int(sq_campanha),
            "match": "sq_campanha",
            "nm_urna_urna": hit[1],
            "sg_partido_urna": hit[2],
            "votos_uf": int(hit[0]),
        }

    nomes = [n for n in (nm_urna, nm_candidato) if n and str(n).strip()]

    # 2) Nome na própria votação do ano/turno/cargo
    for nome in nomes:
        rows = conn.execute(
            """
            SELECT sq_candidato, MAX(nm_urna), MAX(sg_partido), SUM(qt_votos)::bigint AS vt
            FROM eleicao.votacao
            WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND nr_turno = %s
              AND (
                UPPER(TRIM(nm_urna)) = UPPER(TRIM(%s))
                OR UPPER(TRIM(nm_urna)) LIKE '%%' || UPPER(TRIM(%s)) || '%%'
              )
            GROUP BY sq_candidato
            ORDER BY vt DESC
            """,
            (ano, uf, cargo, turno, str(nome).strip(), str(nome).strip()),
        ).fetchall()
        rows = [r for r in rows if _nomes_compativeis(r[1], nome)]
        if rows:
            return {
                "sq_candidato": int(rows[0][0]),
                "match": "nm_urna",
                "nm_urna_urna": rows[0][1],
                "sg_partido_urna": rows[0][2],
                "votos_uf": int(rows[0][3] or 0),
            }

    # 3) Candidatura do ano (mesmo cargo/UF) pelo nome → sq → votos
    for nome in nomes:
        cands = conn.execute(
            """
            SELECT sq_candidato, nm_urna, sg_partido, nr_candidato, nm_candidato
            FROM eleicao.candidatura
            WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s
              AND (
                UPPER(TRIM(nm_urna)) = UPPER(TRIM(%s))
                OR UPPER(TRIM(COALESCE(nm_candidato,''))) = UPPER(TRIM(%s))
              )
            """,
            (ano, uf, cargo, str(nome).strip(), str(nome).strip()),
        ).fetchall()
        cands = [
            r
            for r in cands
            if _nomes_compativeis(r[1], nome) or _nomes_compativeis(r[4], nome)
        ]
        for r in cands:
            sq_i = int(r[0])
            vt = conn.execute(
                """
                SELECT COALESCE(SUM(qt_votos), 0)::bigint
                FROM eleicao.votacao
                WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND nr_turno = %s
                  AND sq_candidato = %s
                """,
                (ano, uf, cargo, turno, sq_i),
            ).fetchone()
            votos = int(vt[0] or 0) if vt else 0
            if votos > 0:
                return {
                    "sq_candidato": sq_i,
                    "match": "candidatura",
                    "nm_urna_urna": r[1],
                    "sg_partido_urna": r[2],
                    "votos_uf": votos,
                }

    # 4) nr_candidato só se o nome na urna for compatível com o da campanha
    if nr_candidato is not None and nomes:
        rows = conn.execute(
            """
            SELECT sq_candidato, MAX(nm_urna), MAX(sg_partido), SUM(qt_votos)::bigint AS vt
            FROM eleicao.votacao
            WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND nr_turno = %s
              AND nr_candidato = %s
            GROUP BY sq_candidato
            ORDER BY vt DESC
            """,
            (ano, uf, cargo, turno, int(nr_candidato)),
        ).fetchall()
        ok = []
        for r in rows:
            if any(_nomes_compativeis(r[1], n) for n in nomes):
                ok.append(r)
            elif sg_partido and (r[2] or "").upper() == str(sg_partido).upper():
                # partido igual + mesmo número ainda exige ao menos 1 token do nome
                if any(_nomes_compativeis(r[1], n) for n in nomes):
                    ok.append(r)
        if ok:
            return {
                "sq_candidato": int(ok[0][0]),
                "match": "nr_e_nome",
                "nm_urna_urna": ok[0][1],
                "sg_partido_urna": ok[0][2],
                "votos_uf": int(ok[0][3] or 0),
            }

    return {
        "sq_candidato": None,
        "match": "nenhum",
        "votos_uf": 0,
        "mensagem": (
            f"Candidato da campanha ({nm_urna or nm_candidato or sq_campanha}"
            + (f", nº {nr_candidato}" if nr_candidato is not None else "")
            + f") não aparece na urna {ano} T{turno} deste cargo — ausência, não zero. "
            "Não usamos outro candidato só porque o número de urna coincidiu."
        ),
    }


def calor_urna(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    ano: int,
    turno: int | None = None,
) -> dict[str, Any]:
    """Calor oficial: % do candidato da campanha por município + detalhe por zona.

    Geometria de zona TSE não está disponível → mapa pinta município;
    zonas entram na tabela lateral (Trilha A: eleicao.votacao).
    """
    from gestao.store import get_status

    st = get_status(conn, campanha_id)
    uf = (st.get("sg_uf") or "AP").upper()[:2]
    cargo = st.get("cd_cargo")
    sq_camp = st.get("sq_candidato")
    if not cargo or not sq_camp:
        return {
            "status": "vazio",
            "mensagem": "Campanha sem cargo/candidato configurado na Gestão.",
            "municipios": [],
            "zonas": [],
            "fonte": "eleicao.votacao",
        }
    if ano not in (2014, 2016, 2018, 2020, 2022, 2024):
        return {
            "status": "vazio",
            "mensagem": f"Ano {ano} fora do recorte de urna.",
            "municipios": [],
            "zonas": [],
        }

    if turno is None or int(turno) <= 0:
        # Majoritário: 1º turno é a âncora (igual motor/perfil). 2º só se pedido.
        if int(cargo) in (1, 3, 11):
            row_t = conn.execute(
                """
                SELECT 1
                FROM eleicao.votacao
                WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND nr_turno = 1
                LIMIT 1
                """,
                (ano, uf, int(cargo)),
            ).fetchone()
            if row_t:
                turno = 1
            else:
                row_t = conn.execute(
                    """
                    SELECT MAX(nr_turno)::int
                    FROM eleicao.votacao
                    WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s
                    """,
                    (ano, uf, int(cargo)),
                ).fetchone()
                if not row_t or row_t[0] is None:
                    return {
                        "status": "vazio",
                        "mensagem": f"Votação inexistente para {uf} cargo={cargo} ano={ano}.",
                        "municipios": [],
                        "zonas": [],
                        "fonte": "eleicao.votacao",
                    }
                turno = int(row_t[0])
        else:
            row_t = conn.execute(
                """
                SELECT MAX(nr_turno)::int
                FROM eleicao.votacao
                WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s
                """,
                (ano, uf, int(cargo)),
            ).fetchone()
            if not row_t or row_t[0] is None:
                return {
                    "status": "vazio",
                    "mensagem": f"Votação inexistente para {uf} cargo={cargo} ano={ano}.",
                    "municipios": [],
                    "zonas": [],
                    "fonte": "eleicao.votacao",
                }
            turno = int(row_t[0])
    else:
        turno = int(turno)

    resolvido = _resolver_sq_na_urna(
        conn,
        ano=ano,
        uf=uf,
        cargo=int(cargo),
        turno=turno,
        sq_campanha=int(sq_camp),
        nr_candidato=st.get("nr_candidato"),
        nm_urna=st.get("nm_urna"),
        nm_candidato=st.get("nm_candidato"),
        sg_partido=st.get("sg_partido"),
    )
    sq = resolvido.get("sq_candidato")
    if not sq:
        # Ainda lista zonas com totais (sem % do candidato) para não fingir zero
        zona_totais = conn.execute(
            """
            SELECT v.nr_zona, MAX(m.nome), COALESCE(SUM(v.qt_votos), 0)::bigint
            FROM eleicao.votacao v
            LEFT JOIN ref.municipio m
              ON m.cd_municipio_tse = v.cd_municipio_tse AND m.sg_uf = v.sg_uf
            WHERE v.ano = %s AND v.sg_uf = %s AND v.cd_cargo = %s AND v.nr_turno = %s
            GROUP BY v.nr_zona
            ORDER BY v.nr_zona
            """,
            (ano, uf, int(cargo), turno),
        ).fetchall()
        zonas = [
            {
                "nr_zona": int(z[0]),
                "composicao": ZONA_AP_COMPOSICAO.get(int(z[0])),
                "municipio_exemplo": z[1],
                "votos_candidato": None,
                "votos_total": int(z[2] or 0),
                "pct": None,
            }
            for z in zona_totais
        ]
        return {
            "status": "vazio",
            "mensagem": resolvido.get("mensagem") or "Candidato inexistente nesta urna.",
            "uf": uf,
            "ano": ano,
            "turno": turno,
            "cd_cargo": int(cargo),
            "cargo_label": st.get("cargo_label"),
            "sq_candidato_campanha": int(sq_camp),
            "sq_candidato": None,
            "match_urna": resolvido.get("match"),
            "nm_urna": st.get("nm_urna") or st.get("nm_candidato"),
            "sg_partido": st.get("sg_partido"),
            "fonte": "eleicao.votacao (Trilha A)",
            "escala": {"min_pct": None, "max_pct": None},
            "municipios": [],
            "zonas": zonas,
        }

    mun_rows = conn.execute(
        """
        SELECT m.cod_ibge, m.nome, m.cd_municipio_tse,
               COALESCE(SUM(v.qt_votos) FILTER (WHERE v.sq_candidato = %s), 0)::bigint AS nosso,
               COALESCE(SUM(v.qt_votos), 0)::bigint AS total
        FROM ref.municipio m
        LEFT JOIN eleicao.votacao v
          ON v.cd_municipio_tse = m.cd_municipio_tse
         AND v.sg_uf = m.sg_uf
         AND v.ano = %s AND v.nr_turno = %s AND v.cd_cargo = %s
        WHERE m.sg_uf = %s
        GROUP BY m.cod_ibge, m.nome, m.cd_municipio_tse
        ORDER BY m.nome
        """,
        (int(sq), ano, turno, int(cargo), uf),
    ).fetchall()

    municipios: list[dict[str, Any]] = []
    for ibge, nome, tse, nosso, total in mun_rows:
        nosso_i = int(nosso or 0)
        total_i = int(total or 0)
        pct = round(100.0 * nosso_i / total_i, 2) if total_i > 0 else None
        municipios.append(
            {
                "cod_ibge": int(ibge),
                "nome": nome,
                "cd_municipio_tse": int(tse) if tse is not None else None,
                "votos_candidato": nosso_i if total_i > 0 else None,
                "votos_total": total_i if total_i > 0 else None,
                "pct": pct,
                "status": "ok" if total_i > 0 else "inexistente",
            }
        )

    zona_rows = conn.execute(
        """
        SELECT v.nr_zona,
               MAX(m.nome) AS municipio_exemplo,
               COALESCE(SUM(v.qt_votos) FILTER (WHERE v.sq_candidato = %s), 0)::bigint AS nosso,
               COALESCE(SUM(v.qt_votos), 0)::bigint AS total
        FROM eleicao.votacao v
        LEFT JOIN ref.municipio m
          ON m.cd_municipio_tse = v.cd_municipio_tse AND m.sg_uf = v.sg_uf
        WHERE v.ano = %s AND v.sg_uf = %s AND v.cd_cargo = %s AND v.nr_turno = %s
        GROUP BY v.nr_zona
        ORDER BY v.nr_zona
        """,
        (int(sq), ano, uf, int(cargo), turno),
    ).fetchall()

    zonas: list[dict[str, Any]] = []
    for nr_zona, mun_ex, nosso, total in zona_rows:
        nosso_i = int(nosso or 0)
        total_i = int(total or 0)
        pct = round(100.0 * nosso_i / total_i, 2) if total_i > 0 else None
        nz = int(nr_zona)
        zonas.append(
            {
                "nr_zona": nz,
                "composicao": ZONA_AP_COMPOSICAO.get(nz),
                "municipio_exemplo": mun_ex,
                "votos_candidato": nosso_i if total_i > 0 else None,
                "votos_total": total_i if total_i > 0 else None,
                "pct": pct,
            }
        )

    # Detalhe zona × município (Macapá tem várias zonas no mesmo IBGE)
    zona_mun_rows = conn.execute(
        """
        SELECT m.cod_ibge, v.nr_zona,
               COALESCE(SUM(v.qt_votos) FILTER (WHERE v.sq_candidato = %s), 0)::bigint,
               COALESCE(SUM(v.qt_votos), 0)::bigint
        FROM eleicao.votacao v
        JOIN ref.municipio m
          ON m.cd_municipio_tse = v.cd_municipio_tse AND m.sg_uf = v.sg_uf
        WHERE v.ano = %s AND v.sg_uf = %s AND v.cd_cargo = %s AND v.nr_turno = %s
        GROUP BY m.cod_ibge, v.nr_zona
        ORDER BY m.cod_ibge, v.nr_zona
        """,
        (int(sq), ano, uf, int(cargo), turno),
    ).fetchall()
    zonas_por_ibge: dict[int, list[dict[str, Any]]] = {}
    for ibge, nz, nosso, total in zona_mun_rows:
        nosso_i = int(nosso or 0)
        total_i = int(total or 0)
        if total_i <= 0:
            continue
        zonas_por_ibge.setdefault(int(ibge), []).append(
            {
                "nr_zona": int(nz),
                "composicao": ZONA_AP_COMPOSICAO.get(int(nz)),
                "votos_candidato": nosso_i,
                "votos_total": total_i,
                "pct": round(100.0 * nosso_i / total_i, 2),
            }
        )
    for m in municipios:
        m["zonas"] = zonas_por_ibge.get(int(m["cod_ibge"]), [])

    pcts = [m["pct"] for m in municipios if m["pct"] is not None]
    nm_exib = resolvido.get("nm_urna_urna") or st.get("nm_urna") or st.get("nm_candidato")
    return {
        "status": "ok" if any(m.get("votos_total") for m in municipios) else "vazio",
        "uf": uf,
        "ano": ano,
        "turno": turno,
        "cd_cargo": int(cargo),
        "cargo_label": st.get("cargo_label"),
        "sq_candidato_campanha": int(sq_camp),
        "sq_candidato": int(sq),
        "match_urna": resolvido.get("match"),
        "nm_urna": nm_exib,
        "sg_partido": resolvido.get("sg_partido_urna") or st.get("sg_partido"),
        "votos_uf_candidato": resolvido.get("votos_uf"),
        "fonte": "eleicao.votacao (Trilha A)",
        "nota": (
            "Calor no mapa = município (malha IBGE). "
            "Detalhe por zona eleitoral na tabela (sem polígono oficial de zona). "
            "pct = votos do candidato / votos nominais+legenda no recorte. Ausência ≠ zero. "
            f"Match urna: {resolvido.get('match')}."
        ),
        "escala": {
            "min_pct": min(pcts) if pcts else None,
            "max_pct": max(pcts) if pcts else None,
        },
        "municipios": municipios,
        "zonas": zonas,
    }