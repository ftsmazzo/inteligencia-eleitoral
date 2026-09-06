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
        "agro_pam_soja_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2711",
        "mun",
    ),
    (
        "agro_pam_milho_t",
        "br_mun_agro_pam",
        "https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/214/p/last/c81/2712",
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


def _mark_pib_comex_counts(conn: psycopg.Connection) -> None:
    try:
        n = conn.execute("SELECT count(*), max(ano)::text FROM contexto.pib_mun").fetchone()
        _upsert_status(conn, "br_mun_pib", "L1", "economia", "online", "municipio", int(n[0]), n[1], "IBGE SIDRA 5938", "contexto.pib_mun")
    except Exception:
        pass
    try:
        n = conn.execute("SELECT count(*), max(ano)::text FROM contexto.comex_uf").fetchone()
        _upsert_status(conn, "br_uf_comex", "L1", "economia", "online", "uf", int(n[0]), n[1], "ComexStat", "contexto.comex_uf")
        # legado mun comex ainda não
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


def _load_sidra_into_indicador(
    conn: psycopg.Connection,
    id_indicador: str,
    id_br: str,
    url: str,
) -> None:
    print(f"[lotes] SIDRA {id_indicador}…")
    ano, rows = _parse_sidra_mun(_fetch(url))
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    filtered = [(a, c, v) for a, c, v in rows if c in cods]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM contexto.indicador_mun WHERE id_indicador = %s AND ano = %s",
            (id_indicador, ano),
        )
        with cur.copy(
            "COPY contexto.indicador_mun (ano, cod_ibge, id_indicador, valor, ds_fonte) FROM STDIN"
        ) as copy:
            for a, c, v in filtered:
                copy.write_row((a, c, id_indicador, v, "ibge_sidra"))
    # status do pack
    n = len(filtered)
    _upsert_status(
        conn,
        id_br,
        "L2",
        "agro",
        "online" if n > 5000 else "parcial",
        "municipio",
        n,
        str(ano) if ano else None,
        "IBGE SIDRA",
        f"indicador {id_indicador}; ausência ≠ zero",
    )
    print(f"[lotes] {id_indicador} ok {n} ano={ano}")


def _load_l2(conn: psycopg.Connection) -> None:
    # fruticultura = subset PAM (laranja 2694 etc.) — marca parcial até produtos fruta
    loaded_pam = False
    for id_ind, id_br, url, _nivel in _SIDRA_LOADS:
        try:
            _load_sidra_into_indicador(conn, id_ind, id_br, url)
            if id_br == "br_mun_agro_pam":
                loaded_pam = True
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[lotes] falha {id_ind}: {exc}")
            _upsert_status(
                conn, id_br, "L2", "agro", "erro", "municipio", None, None, "IBGE SIDRA", str(exc)[:200]
            )
            conn.commit()
    # irrigação / crédito / fruticultura — status explícito
    _upsert_status(
        conn,
        "br_mun_agro_irrigacao",
        "L2",
        "agro",
        "parcial",
        "municipio",
        None,
        None,
        "ANA/Censo Agro",
        "fonte nacional existe; carga Atlas/Censo Agro na fila (próximo ciclo boot)",
    )
    _upsert_status(
        conn,
        "br_mun_agro_credito_rural",
        "L2",
        "agro",
        "parcial",
        "municipio",
        None,
        None,
        "BCB SICOR",
        "fonte nacional existe; carga SICOR na fila",
    )
    _upsert_status(
        conn,
        "br_mun_fruticultura_producao",
        "L2",
        "fruticultura",
        "parcial" if loaded_pam else "carregando",
        "municipio",
        None,
        None,
        "IBGE PAM",
        "subset PAM; produtos fruta na fila",
    )
    _upsert_status(
        conn,
        "br_mun_fruticultura_exportacao",
        "L2",
        "fruticultura",
        "parcial",
        "municipio",
        None,
        None,
        "ComexStat NCM",
        "depende Comex NCM frutas",
    )
    _upsert_status(
        conn,
        "br_mun_fruticultura_poscolheita",
        "fora",
        "fruticultura",
        "bloqueado",
        "municipio",
        None,
        None,
        "—",
        "sem cadastro nacional",
    )
    conn.commit()


def _mark_remaining_explicit(conn: psycopg.Connection) -> None:
    """Garante que lotes ainda não carregados NÃO fiquem como lacuna silenciosa."""
    # Tudo que ainda está 'carregando' há tempo vira 'parcial' com nota de fila —
    # exceto se quisermos manter carregando durante o job.
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


def _load_l3_l7(conn: psycopg.Connection) -> None:
    """Cargas adicionais SIDRA/UF que cabem no boot."""
    extras = [
        # PNAD Contínua — taxa desocupação UF (aprox. tabela 4099 / 6381)
        (
            "pnad_taxa_desocupacao",
            "br_uf_pnad",
            "L1",
            "economia",
            "https://apisidra.ibge.gov.br/values/t/6381/n3/all/v/4099/p/last",
            "uf",
        ),
        # Contas Regionais VAB indústria UF — tabela 5938 já é mun; usar 5938 n3
        (
            "pib_uf_mil",
            "br_uf_industria_contas_regionais",
            "L1",
            "industria",
            "https://apisidra.ibge.gov.br/values/t/5938/n3/all/v/37/p/last",
            "uf",
        ),
    ]
    for id_ind, id_br, lote, tema, url, nivel in extras:
        try:
            print(f"[lotes] {id_ind}…")
            payload = _fetch(url)
            data = json.loads(payload.decode("utf-8"))
            rows_uf: list[tuple] = []
            ano = None
            # mapa código UF IBGE 2 dígitos → sg
            cod_to_sg = {
                "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
                "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
                "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
                "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
            }
            for row in data[1:]:
                cod, a, val = row.get("D1C"), row.get("D3C") or row.get("D2C"), row.get("V")
                # period may be D2C for some tables
                if not a:
                    a = row.get("D2C")
                if not cod or val in (None, "", "...", "-", "..", "X"):
                    continue
                try:
                    ano = int(str(a)[:4])
                    sg = cod_to_sg.get(str(cod).zfill(2)) or cod_to_sg.get(str(cod))
                    if not sg:
                        continue
                    rows_uf.append((ano, sg, id_ind, float(str(val).replace(",", ".")), "ibge_sidra"))
                except ValueError:
                    continue
            if not rows_uf:
                raise RuntimeError("zero linhas")
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM contexto.indicador_uf WHERE id_indicador = %s",
                    (id_ind,),
                )
                with cur.copy(
                    "COPY contexto.indicador_uf (ano, sg_uf, id_indicador, valor, ds_fonte) FROM STDIN"
                ) as copy:
                    for r in rows_uf:
                        copy.write_row(r)
            _upsert_status(
                conn, id_br, lote, tema, "online", "uf", len(rows_uf), str(ano), "IBGE SIDRA", f"indicador {id_ind}"
            )
            conn.commit()
            print(f"[lotes] {id_ind} ok {len(rows_uf)}")
        except Exception as exc:
            conn.rollback()
            print(f"[lotes] falha {id_ind}: {exc}")
            _upsert_status(conn, id_br, lote, tema, "erro", "uf", None, None, "IBGE SIDRA", str(exc)[:200])
            conn.commit()


def _worker() -> None:
    url = _ddl_url()
    if not url:
        print("[lotes] sem DB url")
        return
    try:
        with psycopg.connect(url) as conn:
            _load_l2(conn)
            _load_l3_l7(conn)
            _mark_remaining_explicit(conn)
        print("[lotes] ciclo L2+extras + checklist sem lacuna silenciosa")
    except Exception as exc:
        print(f"[lotes] worker falhou: {exc}")


def ensure_contexto_lotes(background: bool = True) -> None:
    """Chamado no startup do mcp-api após L1."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    # DDL + seed síncrono (rápido); cargas pesadas em thread
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
