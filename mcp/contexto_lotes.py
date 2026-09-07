"""Lotes L0–L8: checklist + carga BR no boot do mcp-api (background).

Critério de pronto: ctl.lote_status cobre 100% do catálogo; nada fica
'silencioso'. status online|parcial|nucleo|bloqueado|trilha_b|erro|carregando.
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import psycopg

# openpyxl só no loader IDEB (falha de import não pode derrubar o boot inteiro)

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_SEED = Path(__file__).resolve().parent / "seed" / "catalogo_brasil.json"
_UA = "inteligencia-eleitoral-brasil/0.3-lotes"
_STARTED = False

# Map status_produto do catálogo → status operacional
_STATUS_MAP = {
    "parcial_nucleo": "nucleo",
    "ausente": "parcial",  # nunca 'carregando' silencioso no seed
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


_PROTECT_STATUS = frozenset({"online", "nucleo", "bloqueado", "trilha_b"})


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
    *,
    preserve_better: bool = False,
) -> None:
    """Grava status. Se preserve_better=True (seed), nunca rebaixa online/nucleo/bloqueado/trilha_b."""
    if preserve_better:
        conn.execute(
            """
            INSERT INTO ctl.lote_status
              (id_br, lote, tema, status, granularidade, linhas, ano_ref, fonte, nota, atualizado_em)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id_br) DO UPDATE SET
              lote = EXCLUDED.lote,
              tema = COALESCE(EXCLUDED.tema, ctl.lote_status.tema),
              fonte = COALESCE(EXCLUDED.fonte, ctl.lote_status.fonte),
              granularidade = COALESCE(ctl.lote_status.granularidade, EXCLUDED.granularidade),
              status = CASE
                WHEN ctl.lote_status.status IN ('online','nucleo','bloqueado','trilha_b')
                  THEN ctl.lote_status.status
                ELSE EXCLUDED.status
              END,
              linhas = CASE
                WHEN ctl.lote_status.status = 'online' THEN ctl.lote_status.linhas
                ELSE COALESCE(EXCLUDED.linhas, ctl.lote_status.linhas)
              END,
              ano_ref = CASE
                WHEN ctl.lote_status.status = 'online' THEN ctl.lote_status.ano_ref
                ELSE COALESCE(EXCLUDED.ano_ref, ctl.lote_status.ano_ref)
              END,
              nota = CASE
                WHEN ctl.lote_status.status IN ('online','nucleo','bloqueado','trilha_b')
                  THEN ctl.lote_status.nota
                ELSE EXCLUDED.nota
              END,
              atualizado_em = now()
            """,
            (id_br, lote, tema, status, granularidade, linhas, ano_ref, fonte, nota),
        )
        return
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
        if st == "parcial" and (b.get("status_produto") == "ausente"):
            nota = ((nota or "") + " | na fila de carga BR (deploy contínuo); não inventar cifra").strip(" |")
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
            preserve_better=True,
        )
        n += 1
    # L1 já em produção
    for id_br, lote, fonte, nota in (
        ("br_mun_pib", "L1", "IBGE SIDRA 5938", "online via contexto_l1"),
        ("br_uf_comex", "L1", "MDIC ComexStat", "online via contexto_l1"),
    ):
        _upsert_status(
            conn, id_br, lote, "economia", "online",
            "municipio" if "mun" in id_br else "uf", None, None, fonte, nota,
        )
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
        ("br_cand_nominata", "ELE", "eleitoral", "SELECT count(*), max(ano)::text FROM eleicao.candidatura", "pessoa"),
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
                if not sg or not vals:
                    continue
                # pega o ano mais recente da série
                anos = sorted(k for k in vals.keys() if str(k).isdigit())
                if not anos:
                    continue
                ano_s = anos[-1]
                try:
                    rows.append((int(ano_s), sg, "pop_uf_estimativa", float(vals[ano_s]), "ibge_agregados"))
                except ValueError:
                    continue
    if not rows:
        raise RuntimeError("pop_uf zero")
    ano_ref = str(max(r[0] for r in rows))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contexto.indicador_uf WHERE id_indicador = %s", ("pop_uf_estimativa",))
        with cur.copy(
            "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    _upsert_status(conn, "br_uf_populacao", "L6", "demografia", "online", "uf", len(rows), ano_ref, "IBGE 6579", "indicador pop_uf_estimativa")
    print(f"[lotes] pop_uf ok {len(rows)} ano={ano_ref}")


def _reconcile_from_indicadores(conn: psycopg.Connection) -> None:
    """Se o indicador já está no banco, marca o id_br como online (mesmo se o seed resetou)."""
    mapping = [
        ("agro_ppm_bovinos", "br_mun_agro_ppm", "L2", "agro"),
        ("agro_pam_soja_t", "br_mun_agro_pam", "L2", "agro"),
        ("agro_pam_milho_t", "br_mun_agro_pam", "L2", "agro"),
        ("agro_pam_cafe_t", "br_mun_agro_pam", "L2", "agro"),
        ("agro_pam_cana_t", "br_mun_agro_pam", "L2", "agro"),
        ("agro_pam_laranja_t", "br_mun_fruticultura_producao", "L2", "fruticultura"),
        ("pib_uf_mil", "br_uf_industria_contas_regionais", "L1", "industria"),
        ("pop_uf_estimativa", "br_uf_populacao", "L6", "demografia"),
        ("fiscal_rreo_anexo1_soma", "br_mun_fiscal_siconfi", "L4", "fiscal"),
        ("pnad_desocupacao_pct", "br_uf_pnad", "L1", "economia"),
        ("pia_unidades_locais", "br_uf_industria_pia", "L1", "industria"),
        ("educ_ideb_ai_pub", "br_mun_educacao_ideb", "L7", "educacao"),
        ("educ_ideb_af_pub", "br_mun_educacao_ideb", "L7", "educacao"),
        ("educ_ideb_em_pub", "br_mun_educacao_ideb", "L7", "educacao"),
        ("energia_potencia_kw", "br_mun_energia_potencia_instalada", "L3", "energia"),
        ("fiscal_seguranca_empenhada", "br_uf_seguranca_gasto", "L5", "seguranca"),
        ("educ_freq_6_17", "br_mun_educacao_censo_escolar", "L7", "educacao"),
        ("agro_irrigacao_ha", "br_mun_agro_irrigacao", "L2", "agro"),
        ("saude_nascidos_vivos", "br_mun_saude_sinasc", "L7", "saude"),
        ("saude_obitos", "br_mun_saude_sim", "L7", "saude"),
        ("vab_industria_mil", "br_uf_industria_contas_regionais", "L1", "industria"),
        ("vab_agropecuaria_mil", "br_uf_agro_contas_regionais", "L2", "agro"),
        ("agro_credito_rural_vl", "br_mun_agro_credito_rural", "L2", "agro"),
        ("fiscal_fpm", "br_mun_fiscal_transferencias", "L4", "fiscal"),
        ("fiscal_fundeb", "br_mun_fiscal_transferencias", "L4", "fiscal"),
        ("fiscal_itr", "br_mun_fiscal_transferencias", "L4", "fiscal"),
        ("pop_mun_estimativa", "br_mun_estimativas", "L6", "demografia"),
        ("energia_gd_potencia_kw", "br_mun_energia_geracao_distribuida", "L3", "energia"),
        ("seguranca_homicidios_dolosos", "br_uf_seguranca_letalidade", "L5", "seguranca"),
        ("turismo_meios_hospedagem", "br_mun_turismo_oferta", "L8", "turismo"),
        ("fiscal_emendas", "br_mun_fiscal_emendas", "L4", "fiscal"),
        ("seguranca_feminicidios", "br_mun_seguranca_mulher", "L5", "seguranca"),
        ("seguranca_roubo_total", "br_mun_seguranca_patrimonial", "L5", "seguranca"),
        ("fiscal_execucao_federal_pago", "br_nac_fiscal_execucao_federal", "L4", "fiscal"),
        ("turismo_pax_origem_uf", "br_aer_turismo_malha_aerea", "L8", "turismo"),
        ("porto_carga_t", "br_por_portos_movimentacao", "L8", "turismo"),
        ("trabalho_caged_saldo", "br_mun_caged", "L1", "trabalho"),
        ("energia_consumo_mwh", "br_mun_energia_consumo", "L3", "energia"),
        ("mineracao_cfem_arrecadado", "br_mun_mineracao_producao", "L8", "mineracao"),
        ("comex_export_fob_usd", "br_mun_comex", "L1", "comercio"),
        ("saude_cnes_estabelecimentos", "br_mun_saude_cnes", "L7", "saude"),
        ("educ_enem_media", "br_mun_educacao_enem", "L7", "educacao"),
        ("prisional_populacao", "br_upr_prisional_sisdepen", "L5", "seguranca"),
    ]
    for id_ind, id_br, lote, tema in mapping:
        try:
            row = conn.execute(
                """
                SELECT count(*), max(ano)::text FROM (
                  SELECT ano FROM contexto.indicador_mun WHERE id_indicador = %s
                  UNION ALL
                  SELECT ano FROM contexto.indicador_uf WHERE id_indicador = %s
                  UNION ALL
                  SELECT ano FROM contexto.indicador_porto WHERE id_indicador = %s
                ) x
                """,
                (id_ind, id_ind, id_ind),
            ).fetchone()
            n = int(row[0] or 0)
            if n <= 0:
                continue
            # só UF no momento → parcial honesto
            if id_br in (
                "br_mun_fiscal_siconfi",
                "br_mun_educacao_censo_escolar",
                "br_mun_saude_sinasc",
                "br_mun_saude_sim",
                "br_mun_agro_credito_rural",
                "br_mun_seguranca_mulher",
                "br_mun_seguranca_patrimonial",
                "br_aer_turismo_malha_aerea",
                "br_mun_energia_consumo",
                "br_upr_prisional_sisdepen",
            ) and n < 1000:
                _upsert_status(
                    conn, id_br, lote, tema, "parcial", "uf", n, row[1],
                    "reconciliado", f"indicador {id_ind} UF presente; capilaridade alvo na fila",
                )
                continue
            if id_br == "br_por_portos_movimentacao":
                gran = "porto"
            elif id_br.startswith("br_mun_"):
                gran = "municipio"
            else:
                gran = "uf"
            _upsert_status(
                conn, id_br, lote, tema, "online" if n >= 20 else "parcial", gran, n, row[1],
                "reconciliado", f"indicador {id_ind} presente",
            )
        except Exception:
            continue
    conn.commit()


def _fetch_timeout(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _load_mun_seed_csv(
    conn: psycopg.Connection,
    filename: str,
    id_ind: str,
    id_br: str,
    lote: str,
    tema: str,
    fonte: str,
    nota: str,
    *,
    online_min: int = 1000,
) -> int:
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / filename
    if not path.exists():
        return 0
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                cod = int(rec["cod_ibge"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if cod not in cods:
                continue
            rows.append((ano, cod, id_ind, val, "seed_csv"))
    if not rows:
        return 0
    _upsert_indicador_mun(
        conn, id_ind, rows, id_br, lote, tema, fonte, nota, online_min=online_min,
    )
    return len(rows)


def _load_fpm_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "fiscal_fpm_mun.csv.gz",
        "fiscal_fpm",
        "br_mun_fiscal_transferencias",
        "L4",
        "fiscal",
        "Tesouro Transparente FPM",
        "FPM anual agregado; ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] fpm seed={n}")


def _load_fundeb_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "fiscal_fundeb_mun.csv.gz",
        "fiscal_fundeb",
        "br_mun_fiscal_transferencias",
        "L4",
        "fiscal",
        "Tesouro Transparente FUNDEB",
        "FUNDEB anual agregado; ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] fundeb seed={n}")


def _load_pop_mun_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "pop_mun_estimativa.csv.gz",
        "pop_mun_estimativa",
        "br_mun_estimativas",
        "L6",
        "demografia",
        "IBGE agregados 6579",
        "população estimada municipal",
        online_min=3000,
    )
    print(f"[lotes] pop mun seed={n}")


def _load_itr_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "fiscal_itr_mun.csv.gz",
        "fiscal_itr",
        "br_mun_fiscal_transferencias",
        "L4",
        "fiscal",
        "Tesouro Transparente ITR",
        "ITR anual agregado; ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] itr seed={n}")


def _load_gd_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "energia_gd_potencia_mun.csv.gz",
        "energia_gd_potencia_kw",
        "br_mun_energia_geracao_distribuida",
        "L3",
        "energia",
        "ANEEL GD",
        "potência instalada GD (kW) por mun; ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] gd seed={n}")


def _load_homicidios_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "seguranca_homicidios_uf.csv.gz",
        "seguranca_homicidios_dolosos",
        "br_uf_seguranca_letalidade",
        "L5",
        "seguranca",
        "FBSP Anuário 2024 T04",
        "homicídios dolosos vítimas 2023; mun MVI na fila",
        status="online",
        gran="uf",
    )
    print(f"[lotes] homicidios seed={n}")


def _load_turismo_hospedagem_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "turismo_hospedagem_mun.csv.gz",
        "turismo_meios_hospedagem",
        "br_mun_turismo_oferta",
        "L8",
        "turismo",
        "CADASTUR meios de hospedagem 4T2025",
        "contagem estabelecimentos por mun; ausência ≠ zero",
        online_min=2000,
    )
    print(f"[lotes] turismo hospedagem seed={n}")


def _load_emendas_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "fiscal_emendas_mun.csv.gz",
        "fiscal_emendas",
        "br_mun_fiscal_emendas",
        "L4",
        "fiscal",
        "Portal Transparência emendas 2024",
        "soma valor empenhado por mun; ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] emendas seed={n}")


def _load_feminicidios_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "seguranca_feminicidios_uf.csv.gz",
        "seguranca_feminicidios",
        "br_mun_seguranca_mulher",
        "L5",
        "seguranca",
        "FBSP Anuário 2024 T23",
        "feminicídios UF 2023; mun na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] feminicidios seed={n}")


def _load_roubo_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "seguranca_roubo_uf.csv.gz",
        "seguranca_roubo_total",
        "br_mun_seguranca_patrimonial",
        "L5",
        "seguranca",
        "FBSP Anuário 2024 T17",
        "roubo total UF 2023; mun na fila (não ratear)",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] roubo seed={n}")


def _load_l0_refs(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / "ref_dicionario_indicadores.csv.gz"
    n_dic = 0
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            n_dic = sum(1 for _ in csv.DictReader(fh))
    if n_dic > 0:
        _upsert_status(
            conn, "ref_dicionario_indicadores", "L0", "referencia", "online", "catalogo",
            n_dic, None, "catalogo_brasil.json", "dicionário gerado do catálogo BR",
        )
    path_g = Path(__file__).resolve().parent / "seed" / "ref_gestoes_federais.csv.gz"
    n_g = 0
    if path_g.exists():
        with gzip.open(path_g, "rt", encoding="utf-8") as fh:
            n_g = sum(1 for _ in csv.DictReader(fh))
    if n_g > 0:
        _upsert_status(
            conn, "ref_gestoes_federais", "L0", "referencia", "online", "nacional",
            n_g, "2026", "seed metadado", "mandatos federais públicos (metadado)",
        )
    print(f"[lotes] l0 refs dic={n_dic} gestoes={n_g}")


def _load_execucao_federal_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "fiscal_execucao_federal_uf.csv.gz",
        "fiscal_execucao_federal_pago",
        "br_nac_fiscal_execucao_federal",
        "L4",
        "fiscal",
        "Portal Transparência despesas 202412",
        "valor pago federal por UF do localizador; ausência ≠ zero",
        status="online",
        gran="uf",
    )
    print(f"[lotes] execucao federal seed={n}")


def _load_malha_aerea_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "turismo_malha_aerea_uf.csv.gz",
        "turismo_pax_origem_uf",
        "br_aer_turismo_malha_aerea",
        "L8",
        "turismo",
        "ANAC Dados Estatísticos",
        "passageiros origem por UF; aeroporto/rota na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] malha aerea seed={n}")


def _load_irrigacao_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn,
        "agro_irrigacao_ha.csv.gz",
        "agro_irrigacao_ha",
        "br_mun_agro_irrigacao",
        "L2",
        "agro",
        "ANA Atlas Irrigação 2021",
        "área total irrigada (ha); ausência ≠ zero",
        online_min=3000,
    )
    print(f"[lotes] irrigacao seed={n}")


def _load_sinasc_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "saude_nascidos_vivos_uf.csv.gz",
        "saude_nascidos_vivos",
        "br_mun_saude_sinasc",
        "L7",
        "saude",
        "IBGE SIDRA 2612",
        "UF nascidos vivos; mun SIM/SINASC na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] sinasc seed={n}")


def _load_obitos_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "saude_obitos_uf.csv.gz",
        "saude_obitos",
        "br_mun_saude_sim",
        "L7",
        "saude",
        "IBGE SIDRA 2685",
        "UF óbitos; mun SIM na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] obitos seed={n}")


def _load_vab_industria_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "vab_industria_uf.csv.gz",
        "vab_industria_mil",
        "br_uf_industria_contas_regionais",
        "L1",
        "industria",
        "IBGE SIDRA 5938",
        "VAB indústria (contas regionais)",
        status="online",
        gran="uf",
    )
    print(f"[lotes] vab industria seed={n}")


def _load_vab_agropecuaria_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "vab_agropecuaria_uf.csv.gz",
        "vab_agropecuaria_mil",
        "br_uf_agro_contas_regionais",
        "L2",
        "agro",
        "IBGE SIDRA 5938 v/513",
        "VAB agropecuária UF (contas regionais); sem inventar mun",
        status="online",
        gran="uf",
    )
    print(f"[lotes] vab agropecuaria seed={n}")


def _load_credito_rural_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "agro_credito_rural_uf.csv.gz",
        "agro_credito_rural_vl",
        "br_mun_agro_credito_rural",
        "L2",
        "agro",
        "BCB SICOR RegiaoUF",
        "UF valor crédito rural; mun SICOR na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] credito rural seed={n}")


def _load_uf_seed_csv(
    conn: psycopg.Connection,
    filename: str,
    id_ind: str,
    id_br: str,
    lote: str,
    tema: str,
    fonte: str,
    nota: str,
    *,
    status: str = "online",
    gran: str = "uf",
    online_min: int = 20,
) -> int:
    """Carrega indicador_uf a partir de mcp/seed/<filename> (ano,sg_uf,id_indicador,valor)."""
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / filename
    if not path.exists():
        return 0
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                sg = str(rec["sg_uf"]).upper()
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if len(sg) != 2:
                continue
            rows.append((ano, sg, id_ind, val, "seed_csv"))
    if not rows:
        return 0
    st = status if len(rows) >= online_min else "parcial"
    if status == "parcial":
        st = "parcial"
    _upsert_indicador_uf(conn, id_ind, rows, id_br, lote, tema, fonte, nota)
    # _upsert_indicador_uf força online se >=20; ajustar se pedimos parcial
    if st == "parcial":
        _upsert_status(conn, id_br, lote, tema, "parcial", gran, len(rows), str(max(r[0] for r in rows)), fonte, nota)
    return len(rows)


def _load_siconfi_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "fiscal_rreo_anexo1_uf.csv.gz",
        "fiscal_rreo_anexo1_soma",
        "br_mun_fiscal_siconfi",
        "L4",
        "fiscal",
        "SICONFI RREO Anexo 01",
        "UF online (soma Anexo 01); mun na fila",
        status="parcial",
        gran="uf",
    )
    print(f"[lotes] siconfi seed a1={n}")


def _load_seguranca_gasto_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn,
        "fiscal_seguranca_empenhada_uf.csv.gz",
        "fiscal_seguranca_empenhada",
        "br_uf_seguranca_gasto",
        "L5",
        "seguranca",
        "SICONFI RREO Anexo 02",
        "despesa Segurança Pública empenhada até 6º bimestre",
        status="online",
        gran="uf",
    )
    print(f"[lotes] seguranca gasto seed={n}")


def _load_educ_freq_uf(conn: psycopg.Connection) -> None:
    """Censo 2022 — pessoas 6–17 que frequentavam escola (SIDRA 10058) por UF."""
    print("[lotes] educ_freq_6_17 UF…")
    url = "https://apisidra.ibge.gov.br/values/t/10058/n3/all/v/13283/p/2022/c58/95253"
    data = json.loads(_fetch(url).decode("utf-8"))
    rows = []
    for row in data[1:]:
        cod, val = row.get("D1C"), row.get("V")
        if not cod or val in (None, "", "...", "-", "..", "X"):
            continue
        sg = COD_TO_SG.get(str(cod).zfill(2))
        if not sg:
            continue
        rows.append((2022, sg, "educ_freq_6_17", float(str(val).replace(",", ".")), "ibge_sidra"))
    if not rows:
        raise RuntimeError("educ_freq zero")
    _upsert_indicador_uf(
        conn, "educ_freq_6_17", rows, "br_mun_educacao_censo_escolar", "L7", "educacao",
        "IBGE SIDRA 10058", "UF: pessoas 6–17 na escola (Censo 2022); mun na fila",
    )
    _upsert_status(
        conn, "br_mun_educacao_censo_escolar", "L7", "educacao", "parcial", "uf",
        len(rows), "2022", "IBGE SIDRA 10058",
        "UF online (freq. escolar 6–17); microdados mun na fila",
    )
    print(f"[lotes] educ_freq ok {len(rows)}")


def _load_siconfi_rreo_uf(conn: psycopg.Connection, ano: int = 2023) -> None:
    """RREO Anexo 01 — valor agregado por UF. Prefere seed; API como fallback."""
    if _count_ind(conn, "fiscal_rreo_anexo1_soma", "uf") >= 20:
        print("[lotes] siconfi já carregado")
        return
    n = _load_uf_seed_csv(
        conn,
        "fiscal_rreo_anexo1_uf.csv.gz",
        "fiscal_rreo_anexo1_soma",
        "br_mun_fiscal_siconfi",
        "L4",
        "fiscal",
        "SICONFI RREO Anexo 01",
        "UF online (soma Anexo 01); mun na fila",
        status="parcial",
        gran="uf",
    )
    if n >= 20:
        print(f"[lotes] siconfi seed ok {n}")
        return
    print("[lotes] SICONFI RREO UF API…")
    id_ind = "fiscal_rreo_anexo1_soma"
    rows = []
    for cod, sg in COD_TO_SG.items():
        url = (
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
            f"?an_exercicio={ano}&nr_periodo=6&co_tipo_demonstrativo=RREO"
            f"&no_anexo=RREO-Anexo%2001&id_ente={int(cod)}"
        )
        try:
            data = json.loads(_fetch_timeout(url, timeout=45).decode("utf-8"))
            items = data.get("items") or []
            total = 0.0
            n_it = 0
            for it in items:
                v = it.get("valor")
                if v is None:
                    continue
                try:
                    total += float(v)
                    n_it += 1
                except (TypeError, ValueError):
                    continue
            if n_it == 0:
                continue
            rows.append((ano, sg, id_ind, total, "siconfi_rreo"))
            print(f"  {sg} ok n={n_it}")
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
        conn, "br_mun_fiscal_siconfi", "L4", "fiscal", "parcial", "uf", len(rows), str(ano),
        "SICONFI RREO", "UF online (soma Anexo 01); mun na fila",
    )
    print(f"[lotes] siconfi ok {len(rows)} UF")


def _count_ind(conn: psycopg.Connection, id_ind: str, table: str = "mun") -> int:
    if table == "uf":
        sql = "SELECT count(*) FROM contexto.indicador_uf WHERE id_indicador = %s"
    elif table == "porto":
        sql = "SELECT count(*) FROM contexto.indicador_porto WHERE id_indicador = %s"
    else:
        sql = "SELECT count(*) FROM contexto.indicador_mun WHERE id_indicador = %s"
    return int(conn.execute(sql, (id_ind,)).fetchone()[0] or 0)


def _ibge6_map(conn: psycopg.Connection) -> dict[int, int]:
    """Mapa código IBGE 6 dígitos → 7 dígitos (ref.municipio)."""
    out: dict[int, int] = {}
    for (cod,) in conn.execute("SELECT cod_ibge FROM ref.municipio"):
        c = int(cod)
        out[c // 10] = c
    return out


def _load_mun6_seed_csv(
    conn: psycopg.Connection,
    filename: str,
    id_ind: str,
    id_br: str,
    lote: str,
    tema: str,
    fonte: str,
    nota: str,
    *,
    online_min: int = 1000,
) -> int:
    """Seed com cod_ibge6 (sem dígito verificador)."""
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / filename
    if not path.exists():
        return 0
    m6 = _ibge6_map(conn)
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                cod6 = int(rec["cod_ibge6"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            cod = m6.get(cod6)
            if not cod:
                continue
            rows.append((ano, cod, id_ind, val, "seed_csv"))
    if not rows:
        return 0
    _upsert_indicador_mun(
        conn, id_ind, rows, id_br, lote, tema, fonte, nota, online_min=online_min,
    )
    return len(rows)


def _ensure_indicador_porto(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contexto.indicador_porto (
          ano smallint NOT NULL,
          nm_porto text NOT NULL,
          sg_uf char(2) NOT NULL,
          id_indicador text NOT NULL,
          valor numeric,
          ds_fonte text NOT NULL,
          PRIMARY KEY (ano, nm_porto, sg_uf, id_indicador)
        )
        """
    )


def _load_porto_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    _ensure_indicador_porto(conn)
    path = Path(__file__).resolve().parent / "seed" / "porto_movimentacao.csv.gz"
    if not path.exists():
        return
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                nome = str(rec["nm_porto"]).strip()
                sg = str(rec["sg_uf"]).upper()[:2]
                id_ind = str(rec["id_indicador"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if not nome or len(sg) != 2:
                continue
            rows.append((ano, nome, sg, id_ind, val, "seed_csv"))
    if not rows:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM contexto.indicador_porto WHERE id_indicador IN ('porto_carga_t','porto_teu')"
        )
        with cur.copy(
            "COPY contexto.indicador_porto (ano, nm_porto, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    n_t = sum(1 for r in rows if r[3] == "porto_carga_t")
    anos = sorted({r[0] for r in rows})
    _upsert_status(
        conn, "br_por_portos_movimentacao", "L8", "turismo",
        "online" if n_t >= 50 else "parcial", "porto", n_t,
        ",".join(str(a) for a in anos),
        "ANTAQ Qlik/Anuário",
        "carga t (+TEU quando houver); 2026 YTD + 2021 anuário; ausência ≠ zero",
    )
    print(f"[lotes] portos seed={len(rows)} carga_t={n_t}")


def _load_energia_consumo_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn, "energia_consumo_uf.csv.gz", "energia_consumo_mwh",
        "br_mun_energia_consumo", "L3", "energia", "EPE",
        "consumo MWh agregado UF (parcial; mun na fila)", status="parcial", gran="uf",
    )
    print(f"[lotes] energia consumo UF seed={n}")


def _load_cfem_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun_seed_csv(
        conn, "mineracao_cfem_mun.csv.gz", "mineracao_cfem_arrecadado",
        "br_mun_mineracao_producao", "L8", "mineracao", "ANM CFEM",
        "ValorRecolhido CFEM agregado mun 2017–2026; sem CPF/CNPJ; ausência ≠ zero",
        online_min=2000,
    )
    print(f"[lotes] cfem seed={n}")


def _load_comex_mun_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    seed_dir = Path(__file__).resolve().parent / "seed"
    path = seed_dir / "comex_mun.csv.gz"
    if not path.exists():
        path = seed_dir / "comex_mun_2024.csv.gz"
    if not path.exists():
        return
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    m6 = _ibge6_map(conn)
    by_ind: dict[str, list[tuple]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                raw = int(rec["cod_ibge"])
                id_ind = str(rec["id_indicador"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            cod = raw if raw in cods else m6.get(raw if raw < 1_000_000 else raw // 10)
            if not cod:
                continue
            by_ind[id_ind].append((ano, cod, id_ind, val, "seed_csv"))
    total = 0
    anos: set[int] = set()
    for id_ind, rows in by_ind.items():
        _upsert_indicador_mun(
            conn, id_ind, rows, "br_mun_comex", "L1", "comercio", "MDIC ComexStat",
            "FOB USD mun 2024–2026 (export/import); ausência ≠ zero", online_min=2000,
        )
        total += len(rows)
        anos.update(r[0] for r in rows)
    if total:
        _upsert_status(
            conn, "br_mun_comex", "L1", "comercio", "online", "municipio", total,
            ",".join(str(a) for a in sorted(anos)),
            "MDIC ComexStat", "FOB USD mun agregado 2024–2026; ausência ≠ zero",
        )
    print(f"[lotes] comex mun seed={total} anos={sorted(anos)}")


def _load_caged_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    seed_dir = Path(__file__).resolve().parent / "seed"
    path = seed_dir / "trabalho_caged_mun.csv.gz"
    if not path.exists():
        n = _load_mun6_seed_csv(
            conn, "trabalho_caged_saldo_mun.csv.gz", "trabalho_caged_saldo",
            "br_mun_caged", "L1", "trabalho", "PDET/CAGED",
            "saldo Jul/2026 por município; ausência ≠ zero", online_min=3000,
        )
        print(f"[lotes] caged seed={n}")
        return
    m6 = _ibge6_map(conn)
    by_ind: dict[str, list[tuple]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                cod6 = int(rec["cod_ibge6"])
                id_ind = str(rec["id_indicador"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            cod = m6.get(cod6)
            if not cod:
                continue
            by_ind[id_ind].append((ano, cod, id_ind, val, "seed_csv"))
    total = 0
    for id_ind, rows in by_ind.items():
        _upsert_indicador_mun(
            conn, id_ind, rows, "br_mun_caged", "L1", "trabalho", "PDET/CAGED",
            "admissões/desligamentos/saldo Jul/2026; ausência ≠ zero", online_min=3000,
        )
        total += len(rows)
    print(f"[lotes] caged seed={total}")


def _load_porto_det_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    _ensure_indicador_porto(conn)
    path = Path(__file__).resolve().parent / "seed" / "porto_movimentacao_det.csv.gz"
    if not path.exists():
        return
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                nome = str(rec["nm_porto"]).strip()
                sg = str(rec["sg_uf"]).upper()[:2]
                id_ind = str(rec["id_indicador"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if not nome or len(sg) != 2:
                continue
            rows.append((ano, nome, sg, id_ind, val, "seed_csv"))
    if not rows:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM contexto.indicador_porto WHERE id_indicador IN ('porto_carga_t_det','porto_teu_det')"
        )
        with cur.copy(
            "COPY contexto.indicador_porto (ano, nm_porto, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    print(f"[lotes] portos detalhe seed={len(rows)}")


def _load_rais_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / "trabalho_rais_estoque_uf.csv.gz"
    if not path.exists():
        return
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        n = sum(1 for _ in csv.DictReader(fh))
    if n < 20:
        print(f"[lotes] rais seed insuficiente n={n}; mantém fila")
        return
    n = _load_uf_seed_csv(
        conn, "trabalho_rais_estoque_uf.csv.gz", "trabalho_rais_estoque",
        "br_mun_rais", "L1", "trabalho", "RAIS/MTE",
        "estoque/vínculos UF (parcial); mun na fila", status="parcial", gran="uf",
    )
    print(f"[lotes] rais UF seed={n}")


def _load_producao_bruta_uf_from_seed(conn: psycopg.Connection) -> None:
    n = _load_uf_seed_csv(
        conn, "mineracao_venda_bruta_uf.csv.gz", "mineracao_venda_bruta_rs",
        "br_mun_mineracao_producao", "L8", "mineracao", "ANM AMB",
        "valor venda bruta UF (série); CFEM mun é âncora", status="parcial", gran="uf",
    )
    # não rebaixar se CFEM já online
    _upsert_status(
        conn, "br_mun_mineracao_producao", "L8", "mineracao", "online", "municipio",
        None, None, "ANM CFEM+AMB", "CFEM mun + venda bruta UF; ausência ≠ zero",
        preserve_better=True,
    )
    print(f"[lotes] producao bruta UF seed={n}")


def _load_cnes_from_seed(conn: psycopg.Connection) -> None:
    n = _load_mun6_seed_csv(
        conn, "saude_cnes_estab_mun.csv.gz", "saude_cnes_estabelecimentos",
        "br_mun_saude_cnes", "L7", "saude", "DATASUS CNES",
        "estabelecimentos Jul/2026 por mun gestor; ausência ≠ zero", online_min=3000,
    )
    print(f"[lotes] cnes seed={n}")


def _load_enem_from_seed(conn: psycopg.Connection) -> None:
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / "educ_enem_mun.csv.gz"
    if not path.exists():
        return
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    by_ind: dict[str, list[tuple]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                cod = int(rec["cod_ibge"])
                id_ind = str(rec["id_indicador"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if cod not in cods:
                continue
            by_ind[id_ind].append((ano, cod, id_ind, val, "seed_csv"))
    total = 0
    for id_ind, rows in by_ind.items():
        _upsert_indicador_mun(
            conn, id_ind, rows, "br_mun_educacao_enem", "L7", "educacao", "INEP ENEM",
            "média notas e inscritos por mun prova 2024; ausência ≠ zero", online_min=1000,
        )
        total += len(rows)
    print(f"[lotes] enem seed={total}")


def _load_sisdepen_from_seed(conn: psycopg.Connection) -> None:
    n_uf = _load_uf_seed_csv(
        conn, "prisional_pop_uf.csv.gz", "prisional_populacao",
        "br_upr_prisional_sisdepen", "L5", "seguranca", "MJ SISDEPEN",
        "população prisional agregada UF 2025; unidade na fila", status="parcial", gran="uf",
    )
    n_mun = _load_mun_seed_csv(
        conn, "prisional_pop_mun.csv.gz", "prisional_populacao_mun",
        "br_upr_prisional_sisdepen", "L5", "seguranca", "MJ SISDEPEN",
        "população prisional agregada mun 2025; unidade na fila", online_min=5000,
    )
    # status honesto: parcial (granularidade alvo = unidade)
    _upsert_status(
        conn, "br_upr_prisional_sisdepen", "L5", "seguranca", "parcial", "uf",
        n_uf, "2025", "MJ SISDEPEN",
        f"pop UF={n_uf} mun={n_mun}; unidade prisional na fila; ausência ≠ zero",
    )
    print(f"[lotes] sisdepen seed uf={n_uf} mun={n_mun}")


def _load_l2(conn: psycopg.Connection) -> None:
    for id_ind, id_br, url, _nivel in _SIDRA_LOADS:
        tema = "fruticultura" if "fruticultura" in id_br else "agro"
        n_exist = _count_ind(conn, id_ind, "mun")
        if n_exist >= 1000:
            print(f"[lotes] skip SIDRA {id_ind} já={n_exist}")
            _upsert_status(
                conn, id_br, "L2", tema, "online", "municipio", n_exist, None,
                "IBGE SIDRA", f"indicador {id_ind} já carregado; skip",
            )
            conn.commit()
            continue
        try:
            _load_sidra_into_indicador(conn, id_ind, id_br, url, lote="L2", tema=tema)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[lotes] falha {id_ind}: {exc}")
            _upsert_status(conn, id_br, "L2", tema, "erro", "municipio", None, None, "IBGE SIDRA", str(exc)[:200])
            conn.commit()
    n_irrig = _count_ind(conn, "agro_irrigacao_ha", "mun")
    if n_irrig < 1000:
        _upsert_status(
            conn, "br_mun_agro_irrigacao", "L2", "agro", "parcial", "municipio", None, None,
            "ANA Atlas Irrigação", "planilha Atlas nacional na fila (sem inventar área)",
            preserve_better=True,
        )
    else:
        _upsert_status(
            conn, "br_mun_agro_irrigacao", "L2", "agro", "online", "municipio", n_irrig, None,
            "ANA Atlas Irrigação 2021", "área total irrigada (ha) já carregada",
        )
    _upsert_status(
        conn, "br_mun_agro_credito_rural", "L2", "agro", "parcial", "municipio", None, None,
        "BCB SICOR", "fonte nacional; carga SICOR na fila",
        preserve_better=True,
    )
    _upsert_status(
        conn, "br_mun_fruticultura_exportacao", "L2", "fruticultura", "parcial", "municipio", None, None,
        "ComexStat NCM", "depende Comex NCM frutas",
        preserve_better=True,
    )
    _upsert_status(
        conn, "br_mun_fruticultura_poscolheita", "fora", "fruticultura", "bloqueado", "municipio", None, None,
        "—", "sem cadastro nacional",
    )
    conn.commit()


def _fold_nome(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _mun_index(conn: psycopg.Connection) -> dict[tuple[str, str], int]:
    idx: dict[tuple[str, str], int] = {}
    for cod, nome, uf in conn.execute(
        "SELECT cod_ibge, nome, sg_uf FROM ref.municipio"
    ):
        if not nome or not uf:
            continue
        idx[(str(uf).upper(), _fold_nome(str(nome)))] = int(cod)
    return idx


def _brnum(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s or s in ("-", "..", "...", "X"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _upsert_indicador_uf(
    conn: psycopg.Connection,
    id_ind: str,
    rows: list[tuple],
    id_br: str,
    lote: str,
    tema: str,
    fonte: str,
    nota: str,
) -> None:
    if not rows:
        raise RuntimeError(f"{id_ind} zero")
    ano_ref = str(max(r[0] for r in rows))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contexto.indicador_uf WHERE id_indicador = %s", (id_ind,))
        with cur.copy(
            "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    _upsert_status(
        conn, id_br, lote, tema, "online" if len(rows) >= 20 else "parcial", "uf",
        len(rows), ano_ref, fonte, nota,
    )


def _upsert_indicador_mun(
    conn: psycopg.Connection,
    id_ind: str,
    rows: list[tuple],
    id_br: str,
    lote: str,
    tema: str,
    fonte: str,
    nota: str,
    online_min: int = 1000,
) -> None:
    if not rows:
        raise RuntimeError(f"{id_ind} zero")
    ano_ref = str(max(r[0] for r in rows))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contexto.indicador_mun WHERE id_indicador = %s", (id_ind,))
        with cur.copy(
            "COPY contexto.indicador_mun (ano, cod_ibge, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    _upsert_status(
        conn, id_br, lote, tema,
        "online" if len(rows) >= online_min else "parcial",
        "municipio", len(rows), ano_ref, fonte, nota,
    )


def _load_pib_uf(conn: psycopg.Connection) -> None:
    print("[lotes] pib_uf…")
    payload = _fetch("https://apisidra.ibge.gov.br/values/t/5938/n3/all/v/37/p/last")
    data = json.loads(payload.decode("utf-8"))
    rows = []
    for row in data[1:]:
        cod, a, val = row.get("D1C"), row.get("D3C"), row.get("V")
        if not cod or val in (None, "", "...", "-", "..", "X"):
            continue
        sg = COD_TO_SG.get(str(cod).zfill(2))
        if not sg:
            continue
        rows.append((int(a), sg, "pib_uf_mil", float(str(val).replace(",", ".")), "ibge_sidra"))
    _upsert_indicador_uf(
        conn, "pib_uf_mil", rows, "br_uf_industria_contas_regionais", "L1", "industria",
        "IBGE SIDRA 5938", "indicador pib_uf_mil",
    )
    print(f"[lotes] pib_uf ok {len(rows)}")


def _load_pnad_uf(conn: psycopg.Connection) -> None:
    print("[lotes] pnad_desocupacao…")
    url = "https://apisidra.ibge.gov.br/values/t/4093/n3/all/v/4099/p/last/c2/6794"
    data = json.loads(_fetch(url).decode("utf-8"))
    rows = []
    for row in data[1:]:
        cod, per, val = row.get("D1C"), row.get("D3C"), row.get("V")
        if not cod or val in (None, "", "...", "-", "..", "X"):
            continue
        sg = COD_TO_SG.get(str(cod).zfill(2))
        if not sg:
            continue
        # trimestre YYYYQN → ano
        ano = int(str(per)[:4])
        rows.append((ano, sg, "pnad_desocupacao_pct", float(str(val).replace(",", ".")), "ibge_sidra"))
    _upsert_indicador_uf(
        conn, "pnad_desocupacao_pct", rows, "br_uf_pnad", "L1", "economia",
        "IBGE SIDRA 4093", "taxa desocupação UF (último trimestre)",
    )
    print(f"[lotes] pnad ok {len(rows)}")


def _load_pia_uf(conn: psycopg.Connection) -> None:
    print("[lotes] pia_unidades…")
    url = "https://apisidra.ibge.gov.br/values/t/1849/n3/all/v/706/p/last"
    data = json.loads(_fetch(url).decode("utf-8"))
    rows = []
    for row in data[1:]:
        cod, a, val = row.get("D1C"), row.get("D3C"), row.get("V")
        if not cod or val in (None, "", "...", "-", "..", "X"):
            continue
        sg = COD_TO_SG.get(str(cod).zfill(2))
        if not sg:
            continue
        rows.append((int(a), sg, "pia_unidades_locais", float(str(val).replace(",", ".")), "ibge_sidra"))
    _upsert_indicador_uf(
        conn, "pia_unidades_locais", rows, "br_uf_industria_pia", "L1", "industria",
        "IBGE SIDRA 1849", "unidades locais industriais UF",
    )
    print(f"[lotes] pia ok {len(rows)}")


_IDEB_PACKS = [
    (
        "educ_ideb_ai_pub",
        "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/2021/divulgacao_anos_iniciais_municipios_2021.zip",
        "divulgacao_anos_iniciais_municipios_2021.xlsx",
    ),
    (
        "educ_ideb_af_pub",
        "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/2021/divulgacao_anos_finais_municipios_2021.zip",
        "divulgacao_anos_finais_municipios_2021.xlsx",
    ),
    (
        "educ_ideb_em_pub",
        "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/2021/divulgacao_ensino_medio_municipios_2021.zip",
        "divulgacao_ensino_medio_municipios_2021.xlsx",
    ),
]


def _load_ideb_from_seed(conn: psycopg.Connection, id_ind: str) -> int:
    """Carga IDEB a partir de mcp/seed/<id>.csv.gz (evita bloqueio INEP na VPS)."""
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / f"{id_ind}.csv.gz"
    if not path.exists():
        return 0
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    rows: list[tuple] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                ano = int(rec["ano"])
                cod = int(rec["cod_ibge"])
                val = float(rec["valor"])
            except (KeyError, TypeError, ValueError):
                continue
            if cod not in cods:
                continue
            rows.append((ano, cod, id_ind, val, "inep_ideb_seed"))
    if not rows:
        return 0
    _upsert_indicador_mun(
        conn, id_ind, rows, "br_mun_educacao_ideb", "L7", "educacao",
        "INEP IDEB 2021 (seed)", f"rede Pública; {id_ind}; seed gzip; ausência ≠ zero",
        online_min=3000,
    )
    return len(rows)


def _ideb_col_index(header: tuple) -> int | None:
    for i, h in enumerate(header):
        hs = str(h or "").upper()
        if "OBSERVADO" in hs:
            return i
        if "IDEB" in hs and "META" not in hs:
            return i
    # fallback: última coluna não-nula do header
    for i in range(len(header) - 1, -1, -1):
        if header[i]:
            return i
    return None


def _load_ideb_mun(conn: psycopg.Connection) -> None:
    print("[lotes] IDEB mun…")
    total = 0
    # 1) seed local (preferencial — funciona na VPS sem INEP)
    for id_ind, _url, _member in _IDEB_PACKS:
        n = _load_ideb_from_seed(conn, id_ind)
        if n:
            print(f"  {id_ind} seed ok {n}")
            total += n
            conn.commit()
    if total >= 3000:
        print(f"[lotes] IDEB via seed total={total}")
        return

    # 2) fallback download INEP
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise RuntimeError(f"openpyxl indisponível e seed insuficiente: {exc}") from exc
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    for id_ind, url, member in _IDEB_PACKS:
        if _count_ind(conn, id_ind, "mun") >= 3000:
            continue
        print(f"  {id_ind} download…")
        blob = _fetch_timeout(url, timeout=180)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
            target = member if member in zf.namelist() else (names[0] if names else None)
            if not target:
                raise RuntimeError(f"xlsx ausente em {url}")
            xdata = zf.read(target)
        wb = load_workbook(io.BytesIO(xdata), read_only=True, data_only=True)
        ws = wb.active
        rows: list[tuple] = []
        ideb_i: int | None = None
        for row in ws.iter_rows(values_only=True):
            if not row or not row[0]:
                continue
            if row[0] == "SG_UF":
                ideb_i = _ideb_col_index(row)
                continue
            if ideb_i is None:
                continue
            if str(row[3] or "").strip() != "Pública":
                continue
            try:
                cod = int(row[1])
            except (TypeError, ValueError):
                continue
            if cod not in cods:
                continue
            ideb = row[ideb_i] if ideb_i < len(row) else None
            if ideb in (None, "", "-", "ND"):
                continue
            try:
                val = float(str(ideb).replace(",", "."))
            except ValueError:
                continue
            rows.append((2021, cod, id_ind, val, "inep_ideb"))
        wb.close()
        _upsert_indicador_mun(
            conn, id_ind, rows, "br_mun_educacao_ideb", "L7", "educacao",
            "INEP IDEB 2021", f"rede Pública; {id_ind}; ausência ≠ zero",
            online_min=3000,
        )
        total += len(rows)
        conn.commit()
        print(f"  {id_ind} ok {len(rows)}")
    print(f"[lotes] IDEB total linhas {total}")


_SIGA_RESOURCE = "11ec447d-698d-4ab8-977f-b424d5deee6a"


def _load_siga_from_seed(conn: psycopg.Connection) -> int:
    import csv
    import gzip

    path = Path(__file__).resolve().parent / "seed" / "energia_potencia_siga.csv.gz"
    if not path.exists():
        return 0
    idx = _mun_index(conn)
    agg: dict[int, float] = defaultdict(float)
    unmatched = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            uf = str(rec.get("sg_uf") or "").upper()
            nome = str(rec.get("nome_mun") or "")
            try:
                pot = float(rec.get("potencia_kw") or 0)
            except ValueError:
                continue
            cod = idx.get((uf, _fold_nome(nome)))
            if cod is None:
                unmatched += 1
                continue
            agg[cod] += pot
    if not agg:
        return 0
    rows = [(2026, cod, "energia_potencia_kw", float(v), "aneel_siga_seed") for cod, v in agg.items()]
    _upsert_indicador_mun(
        conn, "energia_potencia_kw", rows, "br_mun_energia_potencia_instalada", "L3", "energia",
        "ANEEL SIGA (seed)", f"potência fiscalizada kW; unmatched={unmatched}; ausência ≠ zero",
        online_min=500,
    )
    _upsert_status(
        conn, "br_mun_energia_consumo", "L3", "energia", "parcial", "municipio", None, None,
        "EPE", "fila CSV EPE consumo; potência SIGA já online",
        preserve_better=True,
    )
    _upsert_status(
        conn, "br_mun_energia_geracao_distribuida", "L3", "energia", "parcial", "municipio", None, None,
        "ANEEL GD", "zip MMGD ~100MB; staging agregado na fila",
        preserve_better=True,
    )
    print(f"[lotes] SIGA seed ok mun={len(rows)} unmatched={unmatched}")
    return len(rows)


def _load_siga_potencia_mun(conn: psycopg.Connection) -> None:
    """ANEEL SIGA — potência fiscalizada (kW) agregada por município (usinas em Operação)."""
    print("[lotes] ANEEL SIGA potência…")
    n = _load_siga_from_seed(conn)
    if n >= 500:
        return
    idx = _mun_index(conn)
    agg: dict[int, float] = defaultdict(float)
    unmatched = 0
    offset = 0
    page = 5000
    total = None
    while True:
        qs = urllib.parse.urlencode(
            {
                "resource_id": _SIGA_RESOURCE,
                "limit": page,
                "offset": offset,
                "fields": "SigUFPrincipal,DscFaseUsina,MdaPotenciaFiscalizadaKw,DscMuninicpios",
            }
        )
        url = f"https://dadosabertos.aneel.gov.br/api/3/action/datastore_search?{qs}"
        data = json.loads(_fetch_timeout(url, timeout=120).decode("utf-8"))
        if not data.get("success"):
            raise RuntimeError(str(data.get("error"))[:200])
        result = data["result"]
        if total is None:
            total = int(result.get("total") or 0)
        recs = result.get("records") or []
        if not recs:
            break
        for rec in recs:
            fase = str(rec.get("DscFaseUsina") or "")
            if not fase.startswith("Opera"):
                continue
            pot = _brnum(str(rec.get("MdaPotenciaFiscalizadaKw") or ""))
            if pot is None or pot <= 0:
                continue
            uf = str(rec.get("SigUFPrincipal") or "").strip().upper()
            mun_field = str(rec.get("DscMuninicpios") or "").strip()
            first = mun_field.split(",")[0].strip() if mun_field else ""
            nome, uf_m = first, uf
            if " - " in first:
                nome, uf2 = first.rsplit(" - ", 1)
                uf2 = uf2.strip()[:2].upper()
                if len(uf2) == 2:
                    uf_m = uf2
            key = (uf_m, _fold_nome(nome))
            cod = idx.get(key)
            if cod is None:
                unmatched += 1
                continue
            agg[cod] += pot
        offset += len(recs)
        print(f"  page offset={offset}/{total} agg={len(agg)}")
        if offset >= total or len(recs) < page:
            break
    ano = 2026
    rows = [(ano, cod, "energia_potencia_kw", float(v), "aneel_siga") for cod, v in agg.items()]
    _upsert_indicador_mun(
        conn, "energia_potencia_kw", rows, "br_mun_energia_potencia_instalada", "L3", "energia",
        "ANEEL SIGA", f"potência fiscalizada kW; unmatched={unmatched}; ausência ≠ zero",
        online_min=500,
    )
    _upsert_status(
        conn, "br_mun_energia_consumo", "L3", "energia", "parcial", "municipio", None, None,
        "EPE", "fila CSV EPE consumo; potência SIGA já online",
        preserve_better=True,
    )
    _upsert_status(
        conn, "br_mun_energia_geracao_distribuida", "L3", "energia", "parcial", "municipio", None, None,
        "ANEEL GD", "zip MMGD ~100MB; staging agregado na fila",
        preserve_better=True,
    )
    print(f"[lotes] SIGA ok mun={len(rows)} unmatched={unmatched}")


def _load_l3_l8(conn: psycopg.Connection) -> None:
    # Ordem: leves primeiro (não bloquear IDEB/SIGA atrás de SICONFI lento).
    steps: list[tuple] = [
        ("pib_uf", _load_pib_uf, "pib_uf_mil", "uf", 20),
        ("pop_uf", _load_pop_uf_agregados, "pop_uf_estimativa", "uf", 20),
        ("pnad", _load_pnad_uf, "pnad_desocupacao_pct", "uf", 20),
        ("pia", _load_pia_uf, "pia_unidades_locais", "uf", 20),
        ("ideb", _load_ideb_mun, "educ_ideb_ai_pub", "mun", 3000),
        ("siga", _load_siga_potencia_mun, "energia_potencia_kw", "mun", 500),
        ("siconfi", _load_siconfi_rreo_uf, "fiscal_rreo_anexo1_soma", "uf", 20),
    ]
    for label, fn, id_ind, tbl, min_n in steps:
        try:
            n_exist = _count_ind(conn, id_ind, tbl)
            if n_exist >= min_n:
                print(f"[lotes] skip {label} já={n_exist}")
                continue
            print(f"[lotes] run {label}…")
            fn(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[lotes] {label} fail {exc}")
            err_map = {
                "siconfi": ("br_mun_fiscal_siconfi", "L4", "fiscal", "uf", "SICONFI"),
                "ideb": ("br_mun_educacao_ideb", "L7", "educacao", "municipio", "INEP IDEB"),
                "siga": ("br_mun_energia_potencia_instalada", "L3", "energia", "municipio", "ANEEL SIGA"),
                "pnad": ("br_uf_pnad", "L1", "economia", "uf", "IBGE PNAD"),
                "pia": ("br_uf_industria_pia", "L1", "industria", "uf", "IBGE PIA"),
                "pib_uf": ("br_uf_industria_contas_regionais", "L1", "industria", "uf", "IBGE PIB"),
                "pop_uf": ("br_uf_populacao", "L6", "demografia", "uf", "IBGE pop"),
            }
            if label in err_map:
                id_br, lote, tema, gran, fonte = err_map[label]
                _upsert_status(conn, id_br, lote, tema, "erro", gran, None, None, fonte, str(exc)[:200])
            conn.commit()

    for args in (
        ("br_nac_mineral_reservas_mundiais", "L8", "mineracao", "USGS/ANM", "recorte mundial; fora de cifra mun BR auditável no boot"),
        ("br_mun_mineracao_producao", "L8", "mineracao", "ANM AMB/CFEM", "portal ANM 404/SSL no boot; sem inventar"),
        ("br_mun_mineracao_processos", "L8", "mineracao", "ANM SIGMINE", "fila processos minerários"),
        ("br_mun_mineracao_beneficiamento", "L8", "mineracao", "ANM AMB", "fila produção beneficiada"),
        ("br_por_portos_movimentacao", "L8", "turismo", "ANTAQ", "API/anuario ANTAQ indisponível no boot; sem inventar"),
        ("br_mun_caged", "L1", "trabalho", "PDET/CAGED", "SSL/fonte frágil no boot; sem inventar"),
        ("br_mun_rais", "L1", "trabalho", "RAIS", "microdados pesados; staging na fila"),
        ("br_mun_comex", "L1", "comercio", "ComexStat", "API mun 500; UF online em br_uf_comex"),
        ("br_mun_petroleo_gas", "L3", "energia", "ANP", "dados abertos 404 no boot; sem inventar"),
        ("br_nac_fertilizantes_dependencia", "L8", "agro", "ANDA/ComexStat", "ComexStat 403 no boot; sem inventar"),
        ("br_uf_credito_endividamento", "L1", "credito", "BCB", "série UF não auditável no boot; nacional ≠ UF"),
        ("br_mun_mvi", "L5", "seguranca", "SIM/DATASUS", "proxy mun na fila"),
        ("br_mun_educacao_censo_escolar", "L7", "educacao", "INEP Censo Escolar", "fila microdados; UF educ_freq já parcial"),
        ("br_mun_saude_cnes", "L7", "saude", "DATASUS CNES", "fila CNES"),
    ):
        id_br, lote, tema, fonte, nota = args
        st = "bloqueado" if id_br == "br_nac_mineral_reservas_mundiais" else "parcial"
        gran = "municipio" if "_mun_" in id_br else ("porto" if "_por_" in id_br else ("nacional" if "_nac_" in id_br else "uf"))
        _upsert_status(
            conn, id_br, lote, tema, st, gran, None, None, fonte, nota,
            preserve_better=True,
        )
    conn.commit()


def _load_light_sync(conn: psycopg.Connection) -> None:
    """Cargas rápidas no boot (não esperam thread)."""
    for label, fn, id_ind, tbl, min_n in (
        ("pnad", _load_pnad_uf, "pnad_desocupacao_pct", "uf", 20),
        ("pia", _load_pia_uf, "pia_unidades_locais", "uf", 20),
        ("pib_uf", _load_pib_uf, "pib_uf_mil", "uf", 20),
        ("pop_uf", _load_pop_uf_agregados, "pop_uf_estimativa", "uf", 20),
        ("ideb", _load_ideb_mun, "educ_ideb_ai_pub", "mun", 3000),
        ("siga", _load_siga_potencia_mun, "energia_potencia_kw", "mun", 500),
        ("siconfi", _load_siconfi_from_seed, "fiscal_rreo_anexo1_soma", "uf", 20),
        ("seg_gasto", _load_seguranca_gasto_from_seed, "fiscal_seguranca_empenhada", "uf", 20),
        ("educ_freq", _load_educ_freq_uf, "educ_freq_6_17", "uf", 20),
        ("irrig", _load_irrigacao_from_seed, "agro_irrigacao_ha", "mun", 3000),
        ("sinasc", _load_sinasc_from_seed, "saude_nascidos_vivos", "uf", 20),
        ("obitos", _load_obitos_from_seed, "saude_obitos", "uf", 20),
        ("vab_ind", _load_vab_industria_from_seed, "vab_industria_mil", "uf", 20),
        ("vab_agro", _load_vab_agropecuaria_from_seed, "vab_agropecuaria_mil", "uf", 20),
        ("credito", _load_credito_rural_from_seed, "agro_credito_rural_vl", "uf", 20),
        ("fpm", _load_fpm_from_seed, "fiscal_fpm", "mun", 3000),
        ("fundeb", _load_fundeb_from_seed, "fiscal_fundeb", "mun", 3000),
        ("pop_mun", _load_pop_mun_from_seed, "pop_mun_estimativa", "mun", 3000),
        ("itr", _load_itr_from_seed, "fiscal_itr", "mun", 3000),
        ("gd", _load_gd_from_seed, "energia_gd_potencia_kw", "mun", 3000),
        ("homicidios", _load_homicidios_from_seed, "seguranca_homicidios_dolosos", "uf", 20),
        ("turismo", _load_turismo_hospedagem_from_seed, "turismo_meios_hospedagem", "mun", 2000),
        ("emendas", _load_emendas_from_seed, "fiscal_emendas", "mun", 3000),
        ("feminicidios", _load_feminicidios_from_seed, "seguranca_feminicidios", "uf", 20),
        ("roubo", _load_roubo_from_seed, "seguranca_roubo_total", "uf", 20),
        ("exec_fed", _load_execucao_federal_from_seed, "fiscal_execucao_federal_pago", "uf", 20),
        ("malha_aerea", _load_malha_aerea_from_seed, "turismo_pax_origem_uf", "uf", 20),
        ("portos", _load_porto_from_seed, "porto_carga_t", "porto", 9999),
        ("porto_det", _load_porto_det_from_seed, "porto_carga_t_det", "porto", 9999),
        ("caged", _load_caged_from_seed, "trabalho_caged_saldo", "mun", 9999),
        ("energia_cons", _load_energia_consumo_from_seed, "energia_consumo_mwh", "uf", 9999),
        ("cfem", _load_cfem_from_seed, "mineracao_cfem_arrecadado", "mun", 9999),
        ("comex_mun", _load_comex_mun_from_seed, "comex_export_fob_usd", "mun", 9999),
        ("cnes", _load_cnes_from_seed, "saude_cnes_estabelecimentos", "mun", 3000),
        ("enem", _load_enem_from_seed, "educ_enem_media", "mun", 1000),
        ("sisdepen", _load_sisdepen_from_seed, "prisional_populacao", "uf", 9999),
        ("rais", _load_rais_from_seed, "trabalho_rais_estoque", "uf", 9999),
        ("prod_bruta", _load_producao_bruta_uf_from_seed, "mineracao_venda_bruta_rs", "uf", 9999),
    ):
        try:
            force = {
                "portos", "porto_det", "caged", "energia_cons", "cfem",
                "comex_mun", "sisdepen", "rais", "prod_bruta",
            }
            if label not in force and _count_ind(conn, id_ind, tbl) >= min_n:
                print(f"[lotes] sync skip {label}")
                continue
            print(f"[lotes] sync run {label}…")
            fn(conn)
        except Exception as exc:
            print(f"[lotes] sync {label} fail {exc}")
            id_map = {
                "pnad": ("br_uf_pnad", "L1", "economia", "uf"),
                "pia": ("br_uf_industria_pia", "L1", "industria", "uf"),
                "pib_uf": ("br_uf_industria_contas_regionais", "L1", "industria", "uf"),
                "pop_uf": ("br_uf_populacao", "L6", "demografia", "uf"),
                "ideb": ("br_mun_educacao_ideb", "L7", "educacao", "municipio"),
                "siga": ("br_mun_energia_potencia_instalada", "L3", "energia", "municipio"),
                "siconfi": ("br_mun_fiscal_siconfi", "L4", "fiscal", "uf"),
                "seg_gasto": ("br_uf_seguranca_gasto", "L5", "seguranca", "uf"),
                "educ_freq": ("br_mun_educacao_censo_escolar", "L7", "educacao", "uf"),
                "irrig": ("br_mun_agro_irrigacao", "L2", "agro", "municipio"),
                "sinasc": ("br_mun_saude_sinasc", "L7", "saude", "uf"),
                "obitos": ("br_mun_saude_sim", "L7", "saude", "uf"),
                "vab_ind": ("br_uf_industria_contas_regionais", "L1", "industria", "uf"),
                "vab_agro": ("br_uf_agro_contas_regionais", "L2", "agro", "uf"),
                "credito": ("br_mun_agro_credito_rural", "L2", "agro", "uf"),
                "fpm": ("br_mun_fiscal_transferencias", "L4", "fiscal", "municipio"),
                "fundeb": ("br_mun_fiscal_transferencias", "L4", "fiscal", "municipio"),
                "pop_mun": ("br_mun_estimativas", "L6", "demografia", "municipio"),
                "itr": ("br_mun_fiscal_transferencias", "L4", "fiscal", "municipio"),
                "gd": ("br_mun_energia_geracao_distribuida", "L3", "energia", "municipio"),
                "homicidios": ("br_uf_seguranca_letalidade", "L5", "seguranca", "uf"),
                "turismo": ("br_mun_turismo_oferta", "L8", "turismo", "municipio"),
                "emendas": ("br_mun_fiscal_emendas", "L4", "fiscal", "municipio"),
                "feminicidios": ("br_mun_seguranca_mulher", "L5", "seguranca", "uf"),
                "roubo": ("br_mun_seguranca_patrimonial", "L5", "seguranca", "uf"),
                "exec_fed": ("br_nac_fiscal_execucao_federal", "L4", "fiscal", "uf"),
                "malha_aerea": ("br_aer_turismo_malha_aerea", "L8", "turismo", "uf"),
                "portos": ("br_por_portos_movimentacao", "L8", "turismo", "porto"),
                "porto_det": ("br_por_portos_movimentacao", "L8", "turismo", "porto"),
                "caged": ("br_mun_caged", "L1", "trabalho", "municipio"),
                "energia_cons": ("br_mun_energia_consumo", "L3", "energia", "uf"),
                "cfem": ("br_mun_mineracao_producao", "L8", "mineracao", "municipio"),
                "comex_mun": ("br_mun_comex", "L1", "comercio", "municipio"),
                "cnes": ("br_mun_saude_cnes", "L7", "saude", "municipio"),
                "enem": ("br_mun_educacao_enem", "L7", "educacao", "municipio"),
                "sisdepen": ("br_upr_prisional_sisdepen", "L5", "seguranca", "uf"),
                "rais": ("br_mun_rais", "L1", "trabalho", "uf"),
                "prod_bruta": ("br_mun_mineracao_producao", "L8", "mineracao", "uf"),
            }
            if label in id_map:
                id_br, lote, tema, gran = id_map[label]
                _upsert_status(conn, id_br, lote, tema, "erro", gran, None, None, "boot-sync", str(exc)[:200])
    try:
        _load_l0_refs(conn)
    except Exception as exc:
        print(f"[lotes] l0 refs fail {exc}")


def _mark_remaining_explicit(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id_br, lote, tema, fonte, nota FROM ctl.lote_status WHERE status = 'carregando'"
    ).fetchall()
    for id_br, lote, tema, fonte, nota in rows:
        _upsert_status(
            conn, id_br, lote or "L9", tema, "parcial", None, None, None, fonte,
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
            _reconcile_from_indicadores(conn)
            _mark_remaining_explicit(conn)
            # Prioridade: L3+ (PNAD/IDEB/SIGA) antes de re-baixar L2 SIDRA
            try:
                _load_l3_l8(conn)
            except Exception as exc:
                print(f"[lotes] L3-L8: {exc}")
            _reconcile_from_indicadores(conn)
            try:
                _load_l2(conn)
            except Exception as exc:
                print(f"[lotes] L2: {exc}")
            _reconcile_from_indicadores(conn)
            _mark_remaining_explicit(conn)
        print("[lotes] ciclo L3-first + L2 + núcleo sync OK")
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
            print(f"[lotes] checklist seed={n}")
            try:
                _sync_nucleo_from_db(conn)
            except Exception as exc:
                print(f"[lotes] sync nucleo: {exc}")
            try:
                _mark_pib_comex_counts(conn)
            except Exception as exc:
                print(f"[lotes] mark pib: {exc}")
            try:
                _reconcile_from_indicadores(conn)
            except Exception as exc:
                print(f"[lotes] reconcile: {exc}")
            try:
                _load_light_sync(conn)
            except Exception as exc:
                print(f"[lotes] light sync: {exc}")
            try:
                _reconcile_from_indicadores(conn)
            except Exception as exc:
                print(f"[lotes] reconcile2: {exc}")
        print("[lotes] checklist boot OK")
    except Exception as exc:
        print(f"[lotes] seed/reconcile sync falhou: {exc}")

    if background:
        t = threading.Thread(target=_worker, name="contexto-lotes", daemon=True)
        t.start()
        print("[lotes] worker thread started")
    else:
        _worker()
