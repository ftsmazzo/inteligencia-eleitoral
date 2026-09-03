"""Painéis oficiais da campanha — só Trilha A (eleicao.* + contexto.*).

Números nunca vêm de RAG. Ausência = inexistente (não zero inventado).
Desemprego municipal não está no núcleo — não chutar; usar CadÚnico/Bolsa.
"""
from __future__ import annotations

from typing import Any

import psycopg

from gestao.store import get_status

_METRO_AP = ("MACAPA", "MACAPÁ", "SANTANA")


def _norm_nome(s: str) -> str:
    t = (s or "").upper()
    for a, b in (("Á", "A"), ("Ã", "A"), ("Â", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ô", "O"), ("Ú", "U"), ("Ç", "C")):
        t = t.replace(a, b)
    return t


def _regiao(nome: str) -> str:
    n = _norm_nome(nome)
    if n in ("MACAPA", "SANTANA"):
        return "metropolitana"
    return "interior"


def _uf_da_campanha(status: dict[str, Any]) -> str:
    uf = (status.get("sg_uf") or "").strip().upper()
    if not uf or uf == "BR":
        raise ValueError("Painéis exigem UF da campanha (escopo estadual).")
    return uf


def _cargo(status: dict[str, Any]) -> int:
    return int(status.get("cd_cargo") or 3)


def catalogo(status: dict[str, Any]) -> dict[str, Any]:
    uf = status.get("sg_uf") or ""
    cargo = status.get("cargo_label") or "Governador"
    return {
        "status": "ok",
        "uf": uf,
        "candidato": status.get("nm_urna") or status.get("nm_candidato"),
        "paineis": [
            {
                "id": "mapa_forca",
                "titulo": "Mapa de força municipal",
                "para_que": "Onde cada voto pesa mais — eleitorado × quem venceu governador em 2018 e 2022.",
            },
            {
                "id": "perfil_eleitorado",
                "titulo": "Perfil do eleitorado por região",
                "para_que": "Para quem a mensagem precisa falar em cada município (sexo, idade, escolaridade).",
            },
            {
                "id": "socio_voto",
                "titulo": "Indicadores socioeconômicos × voto",
                "para_que": "Onde a dor econômica (CadÚnico / Bolsa) é maior e se isso já reflete na urna.",
            },
        ],
        "nota": f"Recorte: {cargo} · UF {uf}. Fonte: TSE (urna 2018/2022) + MDS (CadÚnico/Bolsa). Sem estimativa.",
    }


def mapa_forca(conn: psycopg.Connection, campanha_id: str, *, ano_eleitorado: int = 2022) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    uf = _uf_da_campanha(st)
    cargo = _cargo(st)
    ano_el = 2022 if ano_eleitorado not in (2018, 2020, 2022, 2024) else ano_eleitorado
    sq_nosso = st.get("sq_candidato")

    mun = conn.execute(
        """
        SELECT m.cod_ibge, m.cd_municipio_tse, m.nome
        FROM ref.municipio m
        WHERE m.sg_uf = %s
        ORDER BY m.nome
        """,
        (uf,),
    ).fetchall()
    if not mun:
        return {"status": "vazio", "mensagem": "Municípios inexistentes neste recorte.", "linhas": []}

    eleit = {
        r[0]: int(r[1] or 0)
        for r in conn.execute(
            """
            SELECT cd_municipio_tse, SUM(qt_eleitores)::bigint
            FROM eleicao.eleitorado
            WHERE ano = %s AND sg_uf = %s
            GROUP BY 1
            """,
            (ano_el, uf),
        ).fetchall()
    }

    turnos = {
        int(r[0]): int(r[1])
        for r in conn.execute(
            """
            SELECT ano, MAX(nr_turno)::int
            FROM eleicao.votacao
            WHERE sg_uf = %s AND cd_cargo = %s AND ano IN (2018, 2022)
            GROUP BY ano
            """,
            (uf, cargo),
        ).fetchall()
    }
    if not turnos:
        return {
            "status": "vazio",
            "mensagem": "Votação de governador 2018/2022 inexistente nesta UF.",
            "linhas": [],
            "fonte": "eleicao.votacao",
        }

    votos = conn.execute(
        """
        SELECT v.ano, v.nr_turno, v.cd_municipio_tse, v.sq_candidato,
               MAX(v.nm_urna), MAX(v.sg_partido), SUM(v.qt_votos)::bigint
        FROM eleicao.votacao v
        WHERE v.sg_uf = %s AND v.cd_cargo = %s AND v.ano IN (2018, 2022)
        GROUP BY 1,2,3,4
        """,
        (uf, cargo),
    ).fetchall()

    por_mun: dict[tuple[int, int, int], list[tuple[int, str, str, int]]] = {}
    totais: dict[tuple[int, int, int], int] = {}
    nosso: dict[tuple[int, int], int] = {}
    for ano, turno, tse, sq, nm, part, qt in votos:
        key = (int(ano), int(turno), int(tse))
        qti = int(qt or 0)
        por_mun.setdefault(key, []).append((int(sq), str(nm or ""), str(part or ""), qti))
        totais[key] = totais.get(key, 0) + qti
        if sq_nosso and int(sq) == int(sq_nosso):
            nosso[(int(ano), int(tse))] = qti

    def _vencedor(ano: int, tse: int) -> dict[str, Any]:
        tr = turnos.get(ano)
        if not tr:
            return {"nome": None, "partido": None, "votos": None, "pct": None, "turno": None, "status": "inexistente"}
        key = (ano, tr, tse)
        lista = por_mun.get(key) or []
        if not lista:
            return {"nome": None, "partido": None, "votos": None, "pct": None, "turno": tr, "status": "inexistente"}
        lista.sort(key=lambda x: -x[3])
        sq, nm, part, qt = lista[0]
        den = totais.get(key) or 0
        pct = round(100.0 * qt / den, 1) if den else None
        return {
            "sq_candidato": sq,
            "nome": nm,
            "partido": part,
            "votos": qt,
            "pct": pct,
            "turno": tr,
            "status": "ok",
        }

    linhas = []
    total_el = sum(eleit.values()) or 1
    for ibge, tse, nome in mun:
        v18 = _vencedor(2018, int(tse))
        v22 = _vencedor(2022, int(tse))
        el = eleit.get(int(tse))
        peso = round(100.0 * (el or 0) / total_el, 2) if el is not None else None
        nosso_v = nosso.get((2022, int(tse)))
        den22 = totais.get((2022, turnos.get(2022, 1), int(tse)))
        nosso_pct = round(100.0 * nosso_v / den22, 1) if nosso_v and den22 else None
        mesmo_vencedor = (
            v18.get("nome") and v22.get("nome") and _norm_nome(v18["nome"]) == _norm_nome(v22["nome"])
        )
        nosso_ganhou = bool(
            sq_nosso and v22.get("sq_candidato") and int(v22["sq_candidato"]) == int(sq_nosso)
        )
        if el is None:
            prioridade = "sem_eleitorado"
            acao = "Eleitorado inexistente neste ano — não ranquear."
        elif nosso_ganhou and (el or 0) >= 20000:
            prioridade = "defender"
            acao = "Base grande onde o nosso venceu em 2022 — proteger presença e serviço."
        elif (not nosso_ganhou) and (el or 0) >= 15000:
            prioridade = "disputar"
            acao = "Muito eleitor e vitória adversária em 2022 — esforço vale o custo."
        elif not mesmo_vencedor:
            prioridade = "virada"
            acao = "Município trocou de lado 2018→2022 — ler o que mudou antes de repetir peça."
        else:
            prioridade = "manter"
            acao = "Peso menor; manter rotina, não drenar agenda da capital."
        linhas.append(
            {
                "cod_ibge": ibge,
                "municipio": nome,
                "regiao": _regiao(nome),
                "eleitores": el,
                "peso_eleitorado_pct": peso,
                "gov_2018": v18,
                "gov_2022": v22,
                "nosso_2022_votos": nosso_v,
                "nosso_2022_pct": nosso_pct,
                "prioridade": prioridade,
                "acao": acao,
            }
        )

    linhas.sort(key=lambda x: -(x["eleitores"] or 0))
    kpis = {
        "municipios": len(linhas),
        "eleitorado_total": sum(x["eleitores"] or 0 for x in linhas),
        "disputar": sum(1 for x in linhas if x["prioridade"] == "disputar"),
        "defender": sum(1 for x in linhas if x["prioridade"] == "defender"),
        "metro_eleitores": sum(x["eleitores"] or 0 for x in linhas if x["regiao"] == "metropolitana"),
    }
    return {
        "status": "ok",
        "uf": uf,
        "cargo": st.get("cargo_label"),
        "candidato": st.get("nm_urna") or st.get("nm_candidato"),
        "ano_eleitorado": ano_el,
        "turnos_usados": turnos,
        "fonte": "eleicao.votacao (governador 2018/2022, último turno) + eleicao.eleitorado",
        "nota": "Percentual sobre votos nominais+legenda somados no município naquele turno. Sem rateio UF→município.",
        "kpis": kpis,
        "linhas": linhas,
    }


def perfil_eleitorado(
    conn: psycopg.Connection, campanha_id: str, *, ano: int = 2022
) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    uf = _uf_da_campanha(st)
    ano = 2022 if ano not in (2018, 2020, 2022, 2024) else ano

    rows = conn.execute(
        """
        SELECT m.cod_ibge, m.nome, m.cd_municipio_tse,
               e.ds_genero, e.ds_faixa_etaria, e.ds_grau_escolaridade,
               e.qt_eleitores
        FROM eleicao.eleitorado e
        JOIN ref.municipio m ON m.cd_municipio_tse = e.cd_municipio_tse AND m.sg_uf = e.sg_uf
        WHERE e.ano = %s AND e.sg_uf = %s
        """,
        (ano, uf),
    ).fetchall()
    if not rows:
        return {"status": "vazio", "mensagem": "Eleitorado inexistente neste recorte.", "linhas": []}

    bag: dict[int, dict[str, Any]] = {}
    for ibge, nome, _tse, gen, faixa, esc, qt in rows:
        d = bag.setdefault(
            int(ibge),
            {
                "cod_ibge": ibge,
                "municipio": nome,
                "regiao": _regiao(nome),
                "total": 0,
                "fem": 0,
                "masc": 0,
                "jovem": 0,
                "idoso": 0,
                "fund_incomp": 0,
                "superior": 0,
            },
        )
        n = int(qt or 0)
        d["total"] += n
        g = (gen or "").upper()
        if "FEM" in g:
            d["fem"] += n
        elif "MASC" in g:
            d["masc"] += n
        f = (faixa or "").upper()
        if any(x in f for x in ("16 ANOS", "17 ANOS", "18 A 20", "21 A 24", "25 A 29")):
            d["jovem"] += n
        if any(x in f for x in ("60 A 64", "65 A 69", "70 A 74", "75 A 79", "80 A 84", "85 A 89", "90 A 94", "95 A 99", "100 ANOS", "SUPERIOR A 79", "SUPERIOR A 70")):
            d["idoso"] += n
        e = (esc or "").upper()
        if "FUNDAMENTAL INCOMPLETO" in e or "LÊ E ESCREVE" in e or "ANALFABET" in e:
            d["fund_incomp"] += n
        if "SUPERIOR COMPLETO" in e:
            d["superior"] += n

    def _pct(part: int, tot: int) -> float | None:
        if tot <= 0:
            return None
        return round(100.0 * part / tot, 1)

    linhas = []
    for d in bag.values():
        tot = d["total"]
        linhas.append(
            {
                "cod_ibge": d["cod_ibge"],
                "municipio": d["municipio"],
                "regiao": d["regiao"],
                "eleitores": tot,
                "pct_feminino": _pct(d["fem"], tot),
                "pct_masculino": _pct(d["masc"], tot),
                "pct_ate_29": _pct(d["jovem"], tot),
                "pct_60_mais": _pct(d["idoso"], tot),
                "pct_baixa_escolaridade": _pct(d["fund_incomp"], tot),
                "pct_superior_completo": _pct(d["superior"], tot),
                "mensagem": (
                    "Peça urbana, serviço e mobilidade."
                    if d["regiao"] == "metropolitana"
                    else "Peça de proximidade; escolaridade e renda pesam mais no tom."
                ),
            }
        )
    linhas.sort(key=lambda x: -(x["eleitores"] or 0))

    def _media(campo: str, regiao: str | None = None) -> float | None:
        xs = [x[campo] for x in linhas if x[campo] is not None and (regiao is None or x["regiao"] == regiao)]
        ws = [x["eleitores"] for x in linhas if x[campo] is not None and (regiao is None or x["regiao"] == regiao)]
        if not xs or not sum(ws):
            return None
        return round(sum(a * b for a, b in zip(xs, ws)) / sum(ws), 1)

    return {
        "status": "ok",
        "uf": uf,
        "ano": ano,
        "fonte": "eleicao.eleitorado (perfil TSE)",
        "nota": "Jovem = faixas até 29 anos. Baixa escolaridade = analfabeto + lê e escreve + fundamental incompleto.",
        "kpis": {
            "municipios": len(linhas),
            "pct_feminino_uf": _media("pct_feminino"),
            "pct_ate_29_uf": _media("pct_ate_29"),
            "pct_feminino_metro": _media("pct_feminino", "metropolitana"),
            "pct_feminino_interior": _media("pct_feminino", "interior"),
            "pct_baixa_esc_interior": _media("pct_baixa_escolaridade", "interior"),
            "pct_baixa_esc_metro": _media("pct_baixa_escolaridade", "metropolitana"),
        },
        "linhas": linhas,
    }


def socio_voto(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    uf = _uf_da_campanha(st)
    cargo = _cargo(st)
    sq_nosso = st.get("sq_candidato")

    anomes_cad = conn.execute("SELECT MAX(anomes) FROM contexto.cadunico_mun").fetchone()[0]
    anomes_bf = conn.execute("SELECT MAX(anomes) FROM contexto.bolsa_familia_mun").fetchone()[0]
    if not anomes_cad and not anomes_bf:
        return {
            "status": "vazio",
            "mensagem": "CadÚnico e Bolsa Família inexistentes neste recorte.",
            "linhas": [],
            "desemprego": "inexistente",
        }

    turno = conn.execute(
        """
        SELECT MAX(nr_turno)::int FROM eleicao.votacao
        WHERE sg_uf = %s AND cd_cargo = %s AND ano = 2022
        """,
        (uf, cargo),
    ).fetchone()
    tr = int(turno[0] or 1) if turno and turno[0] else 1

    votos = conn.execute(
        """
        SELECT v.cd_municipio_tse, v.sq_candidato, MAX(v.nm_urna), MAX(v.sg_partido), SUM(v.qt_votos)::bigint
        FROM eleicao.votacao v
        WHERE v.sg_uf = %s AND v.cd_cargo = %s AND v.ano = 2022 AND v.nr_turno = %s
        GROUP BY 1,2
        """,
        (uf, cargo, tr),
    ).fetchall()
    by_tse: dict[int, list] = {}
    tot: dict[int, int] = {}
    nosso: dict[int, int] = {}
    for tse, sq, nm, part, qt in votos:
        tsei = int(tse)
        qti = int(qt or 0)
        by_tse.setdefault(tsei, []).append((int(sq), str(nm or ""), str(part or ""), qti))
        tot[tsei] = tot.get(tsei, 0) + qti
        if sq_nosso and int(sq) == int(sq_nosso):
            nosso[tsei] = qti

    cad = {}
    if anomes_cad:
        for r in conn.execute(
            """
            SELECT c.cod_ibge, c.qt_familias, c.qt_familias_extrema_pobreza, c.qt_familias_pobreza_pbf
            FROM contexto.cadunico_mun c
            JOIN ref.municipio m ON m.cod_ibge = c.cod_ibge
            WHERE c.anomes = %s AND m.sg_uf = %s
            """,
            (anomes_cad, uf),
        ).fetchall():
            cad[int(r[0])] = {
                "familias": int(r[1] or 0) if r[1] is not None else None,
                "extrema": int(r[2] or 0) if r[2] is not None else None,
                "pobreza_pbf": int(r[3] or 0) if r[3] is not None else None,
            }

    bolsa = {}
    if anomes_bf:
        for r in conn.execute(
            """
            SELECT b.cod_ibge, b.qt_familias, b.qt_pessoas, b.vr_repassado
            FROM contexto.bolsa_familia_mun b
            JOIN ref.municipio m ON m.cod_ibge = b.cod_ibge
            WHERE b.anomes = %s AND m.sg_uf = %s
            """,
            (anomes_bf, uf),
        ).fetchall():
            bolsa[int(r[0])] = {
                "familias": int(r[1] or 0) if r[1] is not None else None,
                "pessoas": int(r[2] or 0) if r[2] is not None else None,
                "repassado": float(r[3]) if r[3] is not None else None,
            }

    mun = conn.execute(
        "SELECT cod_ibge, cd_municipio_tse, nome FROM ref.municipio WHERE sg_uf = %s ORDER BY nome",
        (uf,),
    ).fetchall()

    linhas = []
    for ibge, tse, nome in mun:
        ib, ts = int(ibge), int(tse)
        lista = by_tse.get(ts) or []
        lista.sort(key=lambda x: -x[3])
        den = tot.get(ts) or 0
        venc = lista[0] if lista else None
        c = cad.get(ib) or {}
        b = bolsa.get(ib) or {}
        fam = c.get("familias")
        ext = c.get("extrema")
        taxa_ext = round(100.0 * ext / fam, 1) if fam and ext is not None else None
        nosso_v = nosso.get(ts)
        nosso_pct = round(100.0 * nosso_v / den, 1) if nosso_v and den else None
        if taxa_ext is None:
            leitura = "CadÚnico inexistente neste município — não cruzar."
            oportunidade = None
        elif taxa_ext >= 40 and (nosso_pct is not None and nosso_pct < 45):
            leitura = "Dor econômica alta e urna 2022 não consolidada a nosso favor — ângulo de renda/serviço tem eco."
            oportunidade = "alta"
        elif taxa_ext >= 40:
            leitura = "Dor econômica alta; urna já pesou. Discurso de continuidade de proteção social."
            oportunidade = "defender_pauta"
        elif taxa_ext is not None and taxa_ext < 20:
            leitura = "Menos CadÚnico relativo — mensagem não pode ser só transferência de renda."
            oportunidade = "outra_pauta"
        else:
            leitura = "Dor mediana — cruzar com perfil etário antes de abrir peça econômica."
            oportunidade = "media"
        linhas.append(
            {
                "cod_ibge": ib,
                "municipio": nome,
                "regiao": _regiao(nome),
                "cadunico_familias": fam,
                "cadunico_extrema_pobreza": ext,
                "taxa_extrema_pct": taxa_ext,
                "bolsa_familias": b.get("familias"),
                "bolsa_pessoas": b.get("pessoas"),
                "bolsa_repassado": b.get("repassado"),
                "vencedor_2022": venc[1] if venc else None,
                "vencedor_partido": venc[2] if venc else None,
                "vencedor_pct": round(100.0 * venc[3] / den, 1) if venc and den else None,
                "nosso_2022_pct": nosso_pct,
                "oportunidade": oportunidade,
                "leitura": leitura,
            }
        )

    linhas.sort(key=lambda x: -(x["taxa_extrema_pct"] if x["taxa_extrema_pct"] is not None else -1))
    return {
        "status": "ok",
        "uf": uf,
        "candidato": st.get("nm_urna") or st.get("nm_candidato"),
        "anomes_cadunico": anomes_cad,
        "anomes_bolsa": anomes_bf,
        "turno_2022": tr,
        "desemprego": "inexistente",
        "fonte": "contexto.cadunico_mun + contexto.bolsa_familia_mun (MDS) × eleicao.votacao 2022",
        "nota": (
            "Desemprego municipal não está nesta base (inexistente, não zero). "
            "Dor econômica = famílias em extrema pobreza no CadÚnico / famílias CadÚnico."
        ),
        "kpis": {
            "municipios": len(linhas),
            "oportunidade_alta": sum(1 for x in linhas if x["oportunidade"] == "alta"),
            "familias_cadunico": sum(x["cadunico_familias"] or 0 for x in linhas),
            "familias_bolsa": sum(x["bolsa_familias"] or 0 for x in linhas),
        },
        "linhas": linhas,
    }
