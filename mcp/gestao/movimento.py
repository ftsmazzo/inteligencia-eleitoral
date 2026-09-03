"""Blocos de movimento: ficha territorial única, eleitorado e redes (candidato + adversários)."""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

import psycopg

_ANOS_ELEITORADO = (2014, 2016, 2018, 2020, 2022, 2024, 2026)


def _n(v: int | None) -> str:
    if v is None:
        return "inexistente"
    return f"{int(v):,}".replace(",", ".")


def _pct(a: int, b: int) -> str | None:
    if not a or not b:
        return None
    d = 100.0 * (b - a) / a
    sinal = "+" if d >= 0 else ""
    return f"{sinal}{d:.1f}%".replace(".", ",")


def _delta_txt(a: int | None, b: int | None) -> str:
    if a is None or b is None or a <= 0:
        return "inexistente para comparar"
    d = b - a
    sinal = "+" if d >= 0 else ""
    p = _pct(a, b) or ""
    return f"{sinal}{_n(d)} ({p})"


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


def _canal(url: str) -> str:
    host = ""
    try:
        host = (urlparse(url if "://" in url else "https://" + url).netloc or "").lower()
    except Exception:
        host = (url or "").lower()
    if "instagram" in host:
        return "Instagram"
    if "facebook" in host:
        return "Facebook"
    if host in ("x.com", "twitter.com") or host.endswith(".x.com"):
        return "X"
    if "tiktok" in host:
        return "TikTok"
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    if "threads" in host:
        return "Threads"
    if "whatsapp" in host:
        return "WhatsApp"
    return "Outro"


def _votos_nominais(
    conn: psycopg.Connection, *, uf: str, ano: int, cd_cargo: int, turno: int = 1
) -> int | None:
    row = conn.execute(
        """
        SELECT SUM(v.qt_votos)::bigint
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.sg_uf = %s AND v.cd_cargo = %s AND v.nr_turno = %s
        """,
        (ano, uf, cd_cargo, turno),
    ).fetchone()
    n = int(row[0] or 0) if row else 0
    return n if n > 0 else None


def _cadeiras(
    conn: psycopg.Connection, *, uf: str, ano: int, cd_cargo: int
) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(sg_partido, ''), '(sem partido)'), count(*)::int
        FROM (
          SELECT DISTINCT ON (sq_candidato) sq_candidato, sg_partido
          FROM eleicao.votacao
          WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s
            AND api._eh_eleito(ds_sit_tot_turno)
        ) t
        GROUP BY 1
        ORDER BY 2 DESC, 1
        """,
        (ano, uf, cd_cargo),
    ).fetchall()
    return [(r[0], int(r[1])) for r in rows]


def _eleitos_nomes(
    conn: psycopg.Connection, *, uf: str, ano: int, cd_cargo: int
) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT nm_urna, sg_partido
        FROM (
          SELECT DISTINCT ON (sq_candidato) sq_candidato, nm_urna, sg_partido
          FROM eleicao.votacao
          WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s
            AND api._eh_eleito(ds_sit_tot_turno)
          ORDER BY sq_candidato
        ) t
        ORDER BY nm_urna
        """,
        (ano, uf, cd_cargo),
    ).fetchall()
    return [(r[0] or "", r[1] or "") for r in rows]


def _fmt_cadeiras(linhas: list[tuple[str, int]]) -> str:
    if not linhas:
        return "inexistente"
    total = sum(n for _, n in linhas)
    partes = [f"{sg} {n}" for sg, n in linhas]
    return f"{total} cadeiras — " + "; ".join(partes)


def _movimento_cadeiras(
    ant: list[tuple[str, int]], novo: list[tuple[str, int]]
) -> str:
    a = {k: v for k, v in ant}
    b = {k: v for k, v in novo}
    if not a and not b:
        return "inexistente"
    keys = sorted(set(a) | set(b), key=lambda k: (-(b.get(k, 0)), k))
    bits = []
    for k in keys:
        va, vb = a.get(k, 0), b.get(k, 0)
        if va == vb:
            continue
        d = vb - va
        sinal = "+" if d > 0 else ""
        bits.append(f"{k} {sinal}{d}")
    if not bits:
        return "mesma distribuição de legendas (rótulo TSE, sem consolidar mudanças de nome)."
    return "movimento de cadeiras: " + ", ".join(bits) + "."


def montar_ficha_movimento(conn: psycopg.Connection, *, uf: str) -> dict[str, Any]:
    """Um bloco: 2022 (dep/sen) vs 2018; 2024 (vereador) vs 2020; totais de urna."""
    uf = (uf or "").strip().upper()
    if not uf:
        return {
            "titulo": "Movimento territorial",
            "corpo": "UF inexistente — sem ficha de movimento.",
            "fonte": "eleicao.votacao",
            "nivel": "fato",
            "meta": {"ok": False},
        }

    df18 = _cadeiras(conn, uf=uf, ano=2018, cd_cargo=6)
    df22 = _cadeiras(conn, uf=uf, ano=2022, cd_cargo=6)
    de18 = _cadeiras(conn, uf=uf, ano=2018, cd_cargo=7)
    de22 = _cadeiras(conn, uf=uf, ano=2022, cd_cargo=7)
    sen18 = _eleitos_nomes(conn, uf=uf, ano=2018, cd_cargo=5)
    sen22 = _eleitos_nomes(conn, uf=uf, ano=2022, cd_cargo=5)
    ver20 = _cadeiras(conn, uf=uf, ano=2020, cd_cargo=13)
    ver24 = _cadeiras(conn, uf=uf, ano=2024, cd_cargo=13)

    v_df18 = _votos_nominais(conn, uf=uf, ano=2018, cd_cargo=6)
    v_df22 = _votos_nominais(conn, uf=uf, ano=2022, cd_cargo=6)
    v_de18 = _votos_nominais(conn, uf=uf, ano=2018, cd_cargo=7)
    v_de22 = _votos_nominais(conn, uf=uf, ano=2022, cd_cargo=7)
    v_sen18 = _votos_nominais(conn, uf=uf, ano=2018, cd_cargo=5)
    v_sen22 = _votos_nominais(conn, uf=uf, ano=2022, cd_cargo=5)
    v_ver20 = _votos_nominais(conn, uf=uf, ano=2020, cd_cargo=13)
    v_ver24 = _votos_nominais(conn, uf=uf, ano=2024, cd_cargo=13)
    v_gov18 = _votos_nominais(conn, uf=uf, ano=2018, cd_cargo=3)
    v_gov22 = _votos_nominais(conn, uf=uf, ano=2022, cd_cargo=3)
    v_pref20 = _votos_nominais(conn, uf=uf, ano=2020, cd_cargo=11)
    v_pref24 = _votos_nominais(conn, uf=uf, ano=2024, cd_cargo=11)

    linhas = [
        f"Movimento eleitoral — {uf} (um bloco, Trilha A).",
        "Não é ficha ano a ano: compara a última urna federal/estadual (2022×2018) com a municipal (2024×2020).",
        "Partidos = rótulo TSE da urna; DEM/PR/UNIÃO não são fundidos aqui.",
        "",
        "## Federais e estaduais (2022 vs 2018)",
        f"- Deputado federal, votos nominais 1º turno: { _n(v_df18) } (2018) → { _n(v_df22) } (2022) · {_delta_txt(v_df18, v_df22)}.",
        f"  2018: {_fmt_cadeiras(df18)}.",
        f"  2022: {_fmt_cadeiras(df22)}.",
        f"  {_movimento_cadeiras(df18, df22)}",
        f"- Deputado estadual, votos nominais 1º turno: { _n(v_de18) } (2018) → { _n(v_de22) } (2022) · {_delta_txt(v_de18, v_de22)}.",
        f"  2018: {_fmt_cadeiras(de18)}.",
        f"  2022: {_fmt_cadeiras(de22)}.",
        f"  {_movimento_cadeiras(de18, de22)}",
        f"- Senado, votos nominais 1º turno: { _n(v_sen18) } (2018) → { _n(v_sen22) } (2022) · {_delta_txt(v_sen18, v_sen22)}.",
    ]
    if sen18:
        linhas.append(
            "  Eleitos 2018: " + "; ".join(f"{n} ({p})" for n, p in sen18) + "."
        )
    else:
        linhas.append("  Eleitos 2018: inexistente.")
    if sen22:
        linhas.append(
            "  Eleitos 2022: " + "; ".join(f"{n} ({p})" for n, p in sen22) + "."
        )
    else:
        linhas.append("  Eleitos 2022: inexistente.")

    linhas += [
        "",
        "## Vereadores (2024 vs 2020)",
        f"- Votos nominais 1º turno vereador: { _n(v_ver20) } (2020) → { _n(v_ver24) } (2024) · {_delta_txt(v_ver20, v_ver24)}.",
        f"  2020: {_fmt_cadeiras(ver20)}.",
        f"  2024: {_fmt_cadeiras(ver24)}.",
        f"  {_movimento_cadeiras(ver20, ver24)}",
        "",
        "## Massa de votos (majoritários, 1º turno)",
        f"- Governador: { _n(v_gov18) } (2018) → { _n(v_gov22) } (2022) · {_delta_txt(v_gov18, v_gov22)}.",
        f"- Prefeito (soma UF): { _n(v_pref20) } (2020) → { _n(v_pref24) } (2024) · {_delta_txt(v_pref20, v_pref24)}.",
        "",
        "Leitura: cadeiras e votos andam juntos, mas não são a mesma coisa — proporcional muda com coligação/federação.",
        "Fonte: eleicao.votacao + api._eh_eleito. Ausência = inexistente, não zero.",
    ]

    return {
        "titulo": f"Movimento territorial {uf} · 2018–2024",
        "corpo": "\n".join(linhas),
        "fonte": "eleicao.votacao (Trilha A)",
        "nivel": "fato",
        "meta": {
            "contrato": "ficha_movimento_v1",
            "uf": uf,
            "df_2022": len(df22),
            "ver_2024": sum(n for _, n in ver24),
        },
    }


def montar_eleitorado(conn: psycopg.Connection, *, uf: str) -> dict[str, Any]:
    uf = (uf or "").strip().upper()
    if not uf:
        return {
            "titulo": "Eleitorado",
            "corpo": "UF inexistente.",
            "fonte": "eleicao.eleitorado",
            "nivel": "fato",
            "meta": {},
        }
    mun = conn.execute(
        "SELECT COUNT(*)::int FROM ref.municipio WHERE sg_uf = %s", (uf,)
    ).fetchone()
    n_mun = int(mun[0] or 0) if mun else 0
    rows = conn.execute(
        """
        SELECT ano, SUM(qt_eleitores)::bigint
        FROM eleicao.eleitorado
        WHERE sg_uf = %s AND ano = ANY(%s)
        GROUP BY ano
        ORDER BY ano
        """,
        (uf, list(_ANOS_ELEITORADO)),
    ).fetchall()
    serie: list[tuple[int, int]] = []
    for ano, tot in rows:
        n = int(tot or 0)
        if n > 0:
            serie.append((int(ano), n))

    linhas = [
        f"Eleitorado {uf} — movimento do cadastro TSE (não é urna).",
        f"Municípios na malha: {n_mun or 'inexistente'}.",
        "",
        "## Série oficial",
    ]
    if not serie:
        linhas.append("Inexistente eleitorado nesta UF no recorte.")
        return {
            "titulo": f"Eleitorado {uf}",
            "corpo": "\n".join(linhas),
            "fonte": "eleicao.eleitorado",
            "nivel": "fato",
            "meta": {"municipios": n_mun, "pontos": 0},
        }

    for i, (ano, n) in enumerate(serie):
        if i == 0:
            linhas.append(f"- {ano}: {_n(n)}.")
            continue
        a0, n0 = serie[i - 1]
        linhas.append(f"- {ano}: {_n(n)} · vs {a0}: {_delta_txt(n0, n)}.")

    last_ano, last_n = serie[-1]
    prev = serie[-2] if len(serie) >= 2 else None
    linhas += ["", "## Atual e referência"]
    linhas.append(
        f"Cadastro mais recente no recorte: {last_ano} = {_n(last_n)} (cifra oficial TSE)."
    )

    meta: dict[str, Any] = {
        "municipios": n_mun,
        "serie": [{"ano": a, "n": n} for a, n in serie],
        "atual_oficial_ano": last_ano,
        "atual_oficial": last_n,
    }

    if prev:
        a0, n0 = prev
        anos = last_ano - a0
        if anos > 0 and n0 > 0:
            ritmo = (last_n / n0) ** (1 / anos) - 1
            meta["ritmo_aa"] = round(ritmo, 6)
            linhas.append(
                f"Ritmo {a0}–{last_ano}: {ritmo * 100:+.2f}% ao ano (composto, só cadastro)."
                .replace(".", ",")
            )
            hoje = date.today()
            # Projeção só como referência se o último ponto ainda não for o ano corrente,
            # ou para o horizonte da urna 2026 quando o último oficial é 2024.
            if last_ano < 2026:
                frac = max(0.0, (2026 + (hoje.month - 1) / 12) - last_ano)
                est = int(round(last_n * ((1 + ritmo) ** frac)))
                linhas.append(
                    f"Referência (não é urna, não substitui o TSE): se o mesmo ritmo seguir até 2026, "
                    f"cerca de {_n(est)} eleitores."
                )
                meta["estimativa_ref_2026"] = est
            elif last_ano == 2026 and n0:
                linhas.append(
                    "2026 já está no cadastro — use esse número como atual. "
                    "A linha de ritmo serve só para ler o crescimento, não para inventar eleitor."
                )

    linhas.append(
        "Ausência de um ano na série = dado inexistente neste recorte (não tratar como zero)."
    )
    return {
        "titulo": f"Eleitorado {uf} — movimento",
        "corpo": "\n".join(linhas),
        "fonte": "eleicao.eleitorado",
        "nivel": "fato",
        "meta": meta,
    }


def _redes_sq(conn: psycopg.Connection, ano: int, sq: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ds_url, nr_ordem
        FROM eleicao.rede_social
        WHERE ano = %s AND sq_candidato = %s
        ORDER BY nr_ordem NULLS LAST, ds_url
        LIMIT 40
        """,
        (ano, sq),
    ).fetchall()
    out = []
    for r in rows:
        url = (r[0] or "").strip()
        if not url:
            continue
        out.append({"url": url, "handle_ig": _handle_ig(url), "canal": _canal(url), "ordem": r[1]})
    return out


def _dedup_redes(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in itens:
        k = (r.get("url") or "").strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def montar_redes(
    conn: psycopg.Connection,
    *,
    ano: int,
    sq: int,
    nm_urna: str,
    sg_partido: str | None,
    traj: list[dict[str, Any]],
    concorrentes: list[dict[str, Any]],
) -> dict[str, Any]:
    proprio: list[dict[str, Any]] = []
    for a, s in [(ano, sq)] + [
        (int(t["ano"]), int(t["sq_candidato"]))
        for t in traj
        if t.get("sq_candidato") and int(t["ano"]) <= ano
    ]:
        proprio.extend(_redes_sq(conn, a, s))
    proprio = _dedup_redes(proprio)

    pessoas: list[dict[str, Any]] = [
        {
            "papel": "proprio",
            "nm_urna": nm_urna,
            "sg_partido": sg_partido,
            "sq_candidato": sq,
            "ig": [r["handle_ig"] for r in proprio if r.get("handle_ig")],
            "urls": [r["url"] for r in proprio],
        }
    ]

    adv_blocos: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for c in concorrentes[:12]:
        sq_c = c.get("sq_candidato")
        if not sq_c:
            continue
        redes_c = _dedup_redes(_redes_sq(conn, ano, int(sq_c)))
        pessoa = {
            "papel": "adversario",
            "nm_urna": c.get("nm_urna"),
            "sg_partido": c.get("sg_partido"),
            "sq_candidato": int(sq_c),
            "nr_candidato": c.get("nr_candidato"),
            "ig": [r["handle_ig"] for r in redes_c if r.get("handle_ig")],
            "urls": [r["url"] for r in redes_c],
        }
        pessoas.append(pessoa)
        adv_blocos.append((pessoa, redes_c))

    linhas = [
        "Redes TSE — candidato do escopo e concorrentes (para seed do Radar).",
        "Só URL cadastrada no TSE; lista vazia = inexistente na base, não ausência de rede na vida real.",
        "",
        f"## Próprio — {nm_urna}" + (f" ({sg_partido})" if sg_partido else ""),
    ]
    if proprio:
        for r in proprio:
            extra = f" (IG @{r['handle_ig']})" if r.get("handle_ig") else ""
            linhas.append(f"- {r['canal']}: {r['url']}{extra}")
    else:
        linhas.append("- Inexistente rede TSE neste sq/trajetória.")

    linhas.append("")
    linhas.append("## Adversários (nominata do cargo/UF)")
    if not adv_blocos:
        linhas.append("- Inexistente concorrente com sq.")
    for p, redes_c in adv_blocos:
        rot = f"{p.get('nm_urna')} · {p.get('sg_partido') or '—'} · nº {p.get('nr_candidato') or '—'}"
        linhas.append(f"### {rot}")
        if not redes_c:
            linhas.append("- Inexistente rede TSE.")
            continue
        for r in redes_c:
            extra = f" (IG @{r['handle_ig']})" if r.get("handle_ig") else ""
            linhas.append(f"- {r['canal']}: {r['url']}{extra}")

    ig_all = []
    for p in pessoas:
        ig_all.extend(p.get("ig") or [])

    return {
        "titulo": "Redes TSE — próprio e adversários",
        "corpo": "\n".join(linhas),
        "fonte": "eleicao.rede_social",
        "nivel": "fato",
        "meta": {
            "contrato": "redes_radar_v1",
            "n_proprio": len(proprio),
            "n_adversarios": len(adv_blocos),
            "ig": ig_all,
            "pessoas": pessoas,
        },
    }
