"""Lotes L0–L8: checklist + carga BR no boot do mcp-api (background).

Critério de pronto: ctl.lote_status cobre 100% do catálogo; nada fica
'silencioso'. status online|parcial|nucleo|bloqueado|trilha_b|erro|carregando.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

import psycopg

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_SEED = Path(__file__).resolve().parent / "seed" / "catalogo_brasil.json"
_UA = "inteligencia-eleitoral-brasil/0.3-lotes"
_STARTED = False

# Map status_produto do catálogo → status operacional
_STATUS_MAP = {
    "parcial_nucleo": "nucleo",
    "ausente": "carregando",
    "bloqueado_fonte": "bloqueado",
    "trilha_b_ou_fora": "trilha_b",
    "pendente": "pendente",
    "derivado": "nucleo",
}

# Cargas SIDRA (PAM produtos principais + PPM bovinos)
_SIDRA_LOADS = [
    # (id_indicador, id_br_catalog, url, nivel mun|uf)
    (
        "agro_ppm_bovinos",
        "br_mun_agro_ppm",
        "https://apisidra.ibge.gov.br/values/t/3939/n6/all/v/105/p/last/c79/2670",
        "mun",
    ),
    (
        "agro_pam_milho_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2711",
        "mun",
    ),
    (
        "agro_pam_soja_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2713",
        "mun",
    ),
    (
        "agro_pam_cafe_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2692",
        "mun",
    ),
    (
        "agro_pam_cana_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2696",
        "mun",
    ),
    (
        "agro_pam_laranja_t",
        "br_mun_fruticultura_producao",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2702",
        "mun",
    ),
]


def _ddl_url() -> str | None:
    return (
        os.environ.get("POSTGRES_ADMIN_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("AGENTE_DATABASE_URL")
    )


def _run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    if not path.exists():
        print(f"[lotes] patch ausente: {path}")
        return
    text = path.read_text(encoding="utf-8")
    stmts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in text.splitlines():
        if not in_dollar and line.strip().startswith("--"):
            continue
        parts = line.split("$$")
        if len(parts) > 1 and (len(parts) - 1) % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            buf = []
            if stmt:
                stmts.append(stmt)
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    for stmt in stmts:
        conn.execute(stmt)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.read()


def _parse_sidra_mun(payload: bytes) -> tuple[int | None, list[tuple[int, int, float]]]:
    data = json.loads(payload.decode("utf-8"))
    ano = None
    rows: list[tuple[int, int, float]] = []
    for row in data[1:]:
        cod, a, val = row.get("D1C"), row.get("D3C"), row.get("V")
        if not cod or not a or val in (None, "", "...", "-", "..", "X"):
            continue
        try:
            ano = int(a)
            rows.append((ano, int(cod), float(str(val).replace(",", "."))))
        except ValueError:
            continue
    return ano, rows


def _upsert_status(
    conn: psycopg.Connection,
    id_br: str,
    lote: str,
    tema: str | None,
    status: str,
    granularidade: str | None,
    linhas: int | None,
    ano_ref: str | None,
    fonte: str | None,
    nota: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO ctl.lote_status
          (id_br, lote, tema, status, granularidade, linhas, ano_ref, fonte, nota, atualizado_em)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (id_br) DO UPDATE SET
          lote = EXCLUDED.lote,
          tema = EXCLUDED.tema,
          status = EXCLUDED.status,
          granularidade = EXCLUDED.granularidade,
          linhas = EXCLUDED.linhas,
          ano_ref = EXCLUDED.ano_ref,
          fonte = EXCLUDED.fonte,
          nota = EXCLUDED.nota,
          atualizado_em = now()
        """,
        (id_br, lote, tema, status, granularidade, linhas, ano_ref, fonte, nota),
    )


def _seed_catalog(conn: psycopg.Connection) -> int:
    if not _SEED.exists():
        print("[lotes] catalogo_brasil.json ausente no seed")
        return 0
    cat = json.loads(_SEED.read_text(encoding="utf-8"))
    n = 0
    for b in cat.get("bases") or []:
        id_br = b["id_br"]
        lote = b.get("lote_re_etl") or "fora"
        st = _STATUS_MAP.get(b.get("status_produto") or "", "pendente")
        # já online no produto L1
        if id_br in ("br_mun_pib", "br_uf_comex") or id_br.endswith("_pib") or "comex" in id_br:
            # refine below after checks
            pass
        nota = b.get("nota")
        if st == "bloqueado":
            nota = (nota or "") + " | sem fonte nacional auditável"
        if st == "trilha_b":
            nota = (nota or "") + " | fora da Trilha A (cifra)"
        if st == "nucleo":
            nota = (nota or "") + " | já coberto no núcleo/contexto eleitoral"
        _upsert_status(
            conn,
            id_br=id_br,
            lote=lote,
            tema=b.get("tema"),
            status=st,
            granularidade=b.get("granularidade"),
            linhas=None,
            ano_ref=None,
            fonte=b.get("fonte_br"),
            nota=nota,
        )
        n += 1
    # L1 já em produção
    for id_br, lote, fonte, nota in (
        ("br_mun_pib", "L1", "IBGE SIDRA 5938", "online via contexto_l1"),
        ("br_uf_comex", "L1", "MDIC ComexStat", "online via contexto_l1"),
    ):
        _upsert_status(conn, id_br, lote, "economia", "online", "municipio" if "mun" in id_br else "uf", None, None, fonte, nota)
    return n


COD_TO_SG = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def _mark_pib_comex_counts(conn: psycopg.Connection) -> None:
    try:
        n = conn.execute("SELECT count(*), max(ano)::text FROM contexto.pib_mun").fetchone()
        _upsert_status(conn, "br_mun_pib", "L1", "economia", "online", "municipio", int(n[0]), n[1], "IBGE SIDRA 5938", "contexto.pib_mun")
    except Exception:
        pass
    try:
        n = conn.execute("SELECT count(*), max(ano)::text FROM contexto.comex_uf").fetchone()
        _upsert_status(conn, "br_uf_comex", "L1", "economia", "online", "uf", int(n[0]), n[1], "ComexStat", "contexto.comex_uf")
        _upsert_status(
            conn,
            "br_mun_comex",
            "L1",
            "economia",
            "parcial",
            "municipio",
            None,
            None,
            "ComexStat municipalities",
            "UF online; mun pendente endpoint municipalities",
        )
    except Exception:
        pass


def _sync_nucleo_from_db(conn: psycopg.Connection) -> None:
    """Marca ids do núcleo com contagem real (sem lacuna 'achamos que tem')."""
    checks = [
        ("br_mun_censo", "L6", "demografia", "SELECT count(*), max(ano)::text FROM contexto.populacao_mun WHERE ds_fonte='censo'", "municipio"),
        ("br_mun_estimativas", "L6", "demografia", "SELECT count(*), max(ano)::text FROM contexto.populacao_mun WHERE ds_fonte='estimativa'", "municipio"),
        ("br_mun_cadunico", "L6", "social", "SELECT count(*), max(anomes)::text FROM contexto.cadunico_mun", "municipio"),
        ("br_mun_bolsa_familia", "L6", "social", "SELECT count(*), max(anomes)::text FROM contexto.bolsa_familia_mun", "municipio"),
        ("br_mun_votacao_nominal", "ELE", "eleitoral", "SELECT count(*), max(ano)::text FROM eleicao.votacao", "municipio"),
        ("br_cand_nominata", "ELE", "eleitoral", "SELECT count(*), max(ano)::text FROM eleicao.candidato", "pessoa"),
        ("br_mun_eleitorado_perfil", "ELE", "eleitoral", "SELECT count(*), max(ano)::text FROM eleicao.eleitorado", "municipio"),
        ("br_mun_detalhe_apuracao", "ELE", "eleitoral", "SELECT count(*), max(ano)::text FROM eleicao.detalhe_munzona", "municipio_zona"),
        ("br_depara_tse_ibge", "L0", "referencia", "SELECT count(*), NULL FROM ref.municipio WHERE cd_municipio_tse IS NOT NULL", "municipio"),
        ("br_mun_malha_ibge", "L0", "referencia", "SELECT count(*), NULL FROM ref.municipio", "municipio"),
    ]
    for id_br, lote, tema, sql, gran in checks:
        try:
            n, ano = conn.execute(sql).fetchone()
            st = "online" if int(n or 0) > 0 else "parcial"
            _upsert_status(
                conn, id_br, lote, tema, st, gran, int(n or 0), ano, "nucleo IE-Brasil", "sincronizado do Postgres"
            )
        except Exception as exc:
            _upsert_status(conn, id_br, lote, tema, "parcial", gran, None, None, "nucleo", f"tabela ausente/erro: {exc}"[:180])
    conn.commit()


def _load_sidra_into_indicador(
    conn: psycopg.Connection,
    id_indicador: str,
    id_br: str,
    url: str,
    lote: str = "L2",
    tema: str = "agro",
) -> int:
    print(f"[lotes] SIDRA {id_indicador}…")
    ano, rows = _parse_sidra_mun(_fetch(url))
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    filtered = [(a, c, v) for a, c, v in rows if c in cods]
    with conn.cursor() as cur:
        if ano is not None:
            cur.execute(
                "DELETE FROM contexto.indicador_mun WHERE id_indicador = %s AND ano = %s",
                (id_indicador, ano),
            )
        with cur.copy(
            "COPY contexto.indicador_mun (ano, cod_ibge, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for a, c, v in filtered:
                copy.write_row((a, c, id_indicador, v, "ibge_sidra"))
    n = len(filtered)
    _upsert_status(
        conn,
        id_br,
        lote,
        tema,
        "online" if n >= 1000 else "parcial",
        "municipio",
        n,
        str(ano) if ano else None,
        "IBGE SIDRA",
        f"indicador {id_indicador}; ausência ≠ zero",
    )
    print(f"[lotes] {id_indicador} ok {n} ano={ano}")
    return n


def _load_pop_uf_agregados(conn: psycopg.Connection) -> None:
    print("[lotes] pop_uf agregados…")
    url = "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/2024/variaveis/9324?localidades=N3[all]"
    data = json.loads(_fetch(url).decode("utf-8"))
    rows = []
    for bloco in data:
        for res in bloco.get("resultados") or []:
            for serie in res.get("series") or []:
                loc = serie.get("localidade") or {}
                cod = str(loc.get("id") or "")
                sg = COD_TO_SG.get(cod.zfill(2))
                vals = serie.get("serie") or {}
                if not sg or "2024" not in vals:
                    continue
                try:
                    rows.append((2024, sg, "pop_uf_estimativa", float(vals["2024"]), "ibge_agregados"))
                except ValueError:
                    continue
    if not rows:
        raise RuntimeError("pop_uf zero")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contexto.indicador_uf WHERE id_indicador = %s", ("pop_uf_estimativa",))
        with cur.copy(
            "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    _upsert_status(conn, "br_uf_populacao", "L6", "demografia", "online", "uf", len(rows), "2024", "IBGE 6579", "indicador pop_uf_estimativa")
    print(f"[lotes] pop_uf ok {len(rows)}")


def _load_siconfi_rreo_uf(conn: psycopg.Connection, ano: int = 2023) -> None:
    """RREO Anexo 01 — valor agregado por UF (esfera estadual)."""
    print("[lotes] SICONFI RREO UF…")
    id_ind = "fiscal_rreo_anexo1_soma"
    rows = []
    for cod, sg in COD_TO_SG.items():
        url = (
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
            f"?an_exercicio={ano}&nr_periodo=6&co_tipo_demonstrativo=RREO"
            f"&no_anexo=RREO-Anexo%2001&id_ente={int(cod)}"
        )
        try:
            data = json.loads(_fetch(url).decode("utf-8"))
            items = data.get("items") or []
            total = 0.0
            n = 0
            for it in items:
                v = it.get("valor")
                if v is None:
                    continue
                try:
                    total += float(v)
                    n += 1
                except (TypeError, ValueError):
                    continue
            if n == 0:
                continue
            rows.append((ano, sg, id_ind, total, "siconfi_rreo"))
            print(f"  {sg} ok linhas_rreo={n}")
        except Exception as exc:
            print(f"  {sg} fail {exc}")
    if not rows:
        raise RuntimeError("siconfi zero")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contexto.indicador_uf WHERE id_indicador = %s", (id_ind,))
        with cur.copy(
            "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    _upsert_status(
        conn,
        "br_mun_fiscal_siconfi",
        "L4",
        "fiscal",
        "parcial",
        "uf",
        len(rows),
        str(ano),
        "SICONFI RREO",
        "UF online (soma Anexo 01); mun na fila (API por ente)",
    )
    _upsert_status(
        conn,
        "br_nac_fiscal_execucao_federal",
        "L4",
        "fiscal",
        "parcial",
        "nacional",
        None,
        None,
        "STN/SIAFI",
        "fila; SICONFI UF já parcial",
    )
    print(f"[lotes] siconfi ok {len(rows)} UF")


def _load_l2(conn: psycopg.Connection) -> None:
    for id_ind, id_br, url, _nivel in _SIDRA_LOADS:
        tema = "fruticultura" if "fruticultura" in id_br else "agro"
        try:
            _load_sidra_into_indicador(conn, id_ind, id_br, url, lote="L2", tema=tema)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[lotes] falha {id_ind}: {exc}")
            _upsert_status(conn, id_br, "L2", tema, "erro", "municipio", None, None, "IBGE SIDRA", str(exc)[:200])
            conn.commit()
    _upsert_status(
        conn, "br_mun_agro_irrigacao", "L2", "agro", "parcial", "municipio", None, None,
        "ANA/Censo Agro", "fonte nacional; carga Atlas na fila",
    )
    _upsert_status(
        conn, "br_mun_agro_credito_rural", "L2", "agro", "parcial", "municipio", None, None,
        "BCB SICOR", "fonte nacional; carga SICOR na fila",
    )
    _upsert_status(
        conn, "br_mun_fruticultura_exportacao", "L2", "fruticultura", "parcial", "municipio", None, None,
        "ComexStat NCM", "depende Comex NCM frutas",
    )
    _upsert_status(
        conn, "br_mun_fruticultura_poscolheita", "fora", "fruticultura", "bloqueado", "municipio", None, None,
        "—", "sem cadastro nacional",
    )
    conn.commit()


def _load_l3_l8(conn: psycopg.Connection) -> None:
    # PIB UF
    try:
        print("[lotes] pib_uf…")
        payload = _fetch("https://apisidra.ibge.gov.br/values/t/5938/n3/all/v/37/p/last")
        data = json.loads(payload.decode("utf-8"))
        rows = []
        ano = None
        for row in data[1:]:
            cod, a, val = row.get("D1C"), row.get("D3C"), row.get("V")
            if not cod or val in (None, "", "...", "-", "..", "X"):
                continue
            sg = COD_TO_SG.get(str(cod).zfill(2))
            if not sg:
                continue
            ano = int(a)
            rows.append((ano, sg, "pib_uf_mil", float(str(val).replace(",", ".")), "ibge_sidra"))
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contexto.indicador_uf WHERE id_indicador = %s", ("pib_uf_mil",))
            with cur.copy(
                "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
            ) as copy:
                for r in rows:
                    copy.write_row(r)
        _upsert_status(
            conn, "br_uf_industria_contas_regionais", "L1", "industria", "online", "uf",
            len(rows), str(ano), "IBGE SIDRA 5938", "indicador pib_uf_mil",
        )
        conn.commit()
        print(f"[lotes] pib_uf ok {len(rows)}")
    except Exception as exc:
        conn.rollback()
        print(f"[lotes] pib_uf fail {exc}")

    try:
        _load_pop_uf_agregados(conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[lotes] pop_uf fail {exc}")
        _upsert_status(conn, "br_uf_populacao", "L6", "demografia", "erro", "uf", None, None, "IBGE", str(exc)[:200])
        conn.commit()

    try:
        _load_siconfi_rreo_uf(conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[lotes] siconfi fail {exc}")
        _upsert_status(conn, "br_mun_fiscal_siconfi", "L4", "fiscal", "erro", "uf", None, None, "SICONFI", str(exc)[:200])
        conn.commit()

    # Energia / segurança / saúde — status explícito + o que der
    _upsert_status(
        conn, "br_mun_energia_consumo", "L3", "energia", "parcial", "municipio", None, None,
        "EPE/ANEEL", "fonte nacional; granularidade mun a confirmar — fila CSV EPE",
    )
    _upsert_status(
        conn, "br_mun_energia_geracao_distribuida", "L3", "energia", "parcial", "municipio", None, None,
        "ANEEL GD", "fila dados abertos ANEEL",
    )
    _upsert_status(
        conn, "br_uf_mvi", "L5", "seguranca", "parcial", "uf", None, None,
        "FBSP/SIM", "FBSP tipicamente UF; carga anuário na fila",
    )
    _upsert_status(
        conn, "br_mun_mvi", "L5", "seguranca", "parcial", "municipio", None, None,
        "SIM/DATASUS", "proxy mun na fila; não confundir com FBSP",
    )
    _upsert_status(
        conn, "br_mun_educacao_ideb", "L7", "educacao", "parcial", "municipio", None, None,
        "INEP IDEB", "fila download INEP",
    )
    _upsert_status(
        conn, "br_mun_educacao_censo_escolar", "L7", "educacao", "parcial", "municipio", None, None,
        "INEP Censo Escolar", "fila microdados INEP",
    )
    _upsert_status(
        conn, "br_mun_saude_cnes", "L7", "saude", "parcial", "municipio", None, None,
        "DATASUS CNES", "fila CNES",
    )
    _upsert_status(
        conn, "br_por_portos_movimentacao", "L8", "turismo", "parcial", "porto", None, None,
        "ANTAQ", "checar painel operacional; fila",
    )
    conn.commit()


def _mark_remaining_explicit(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id_br, lote, tema, fonte, nota FROM ctl.lote_status WHERE status = 'carregando'"
    ).fetchall()
    for id_br, lote, tema, fonte, nota in rows:
        _upsert_status(
            conn,
            id_br,
            lote or "L9",
            tema,
            "parcial",
            None,
            None,
            None,
            fonte,
            (nota or "") + " | na fila de carga BR (deploy contínuo); não inventar cifra",
        )
    conn.commit()


def _worker() -> None:
    url = _ddl_url()
    if not url:
        print("[lotes] sem DB url")
        return
    try:
        with psycopg.connect(url) as conn:
            _sync_nucleo_from_db(conn)
            _mark_pib_comex_counts(conn)
            _load_l2(conn)
            _load_l3_l8(conn)
            _mark_remaining_explicit(conn)
        print("[lotes] ciclo L2–L8 + núcleo sync OK")
    except Exception as exc:
        print(f"[lotes] worker falhou: {exc}")


def ensure_contexto_lotes(background: bool = True) -> None:
    """Chamado no startup do mcp-api após L1."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_file(conn, _SQL_DIR / "patch_contexto_lotes.sql")
            n = _seed_catalog(conn)
            _mark_pib_comex_counts(conn)
            print(f"[lotes] checklist seed={n}")
    except Exception as exc:
        print(f"[lotes] seed sync falhou: {exc}")

    if background:
        t = threading.Thread(target=_worker, name="contexto-lotes", daemon=True)
        t.start()
    else:
        _worker()
