"""Contexto L1 (PIB + Comex) — DDL no boot do mcp-api + carga se vazio.

Rodado no startup do deploy EasyPanel. Sem terminal do usuário.
Escopo BR; não promove NE9.
"""
from __future__ import annotations

import json
import os
import unicodedata
import urllib.request
from pathlib import Path

import psycopg

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_UA = "inteligencia-eleitoral-brasil/0.2-mcp-boot"
_READY = False

UF_NOME = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "distrito federal": "DF",
    "espirito santo": "ES",
    "goias": "GO",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "para": "PA",
    "paraiba": "PB",
    "parana": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
    "nao declarada": "XX",
    "exterior": "ZZ",
}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or os.environ.get("DATABASE_URL") or os.environ.get(
        "AGENTE_DATABASE_URL"
    )


def _run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Executa script SQL multi-statement respeitando blocos $$ ... $$."""
    if not path.exists():
        print(f"[contexto-l1] patch ausente: {path}")
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


def _post_json(url: str, body: dict) -> bytes:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _parse_sidra(payload: bytes) -> dict[tuple[int, int], float]:
    data = json.loads(payload.decode("utf-8"))
    out: dict[tuple[int, int], float] = {}
    for row in data[1:]:
        cod, ano, val = row.get("D1C"), row.get("D3C"), row.get("V")
        if not cod or not ano or val in (None, "", "...", "-"):
            continue
        try:
            out[(int(ano), int(cod))] = float(str(val).replace(",", "."))
        except ValueError:
            continue
    return out


def _load_pib(conn: psycopg.Connection) -> None:
    n = conn.execute("SELECT count(*) FROM contexto.pib_mun").fetchone()[0]
    if int(n) > 0:
        print(f"[contexto-l1] pib já carregado ({n} linhas)")
        return
    print("[contexto-l1] baixando PIB SIDRA 5938…")
    pib = _parse_sidra(
        _fetch("https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/last")
    )
    pc = _parse_sidra(
        _fetch("https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/543/p/last")
    )
    cods = {r[0] for r in conn.execute("SELECT cod_ibge FROM ref.municipio")}
    rows = []
    for key in sorted(set(pib) | set(pc)):
        ano, cod = key
        if cod not in cods:
            continue
        rows.append((ano, cod, pib.get(key), pc.get(key), "ibge_sidra_5938"))
    with conn.cursor() as cur:
        with cur.copy(
            "COPY contexto.pib_mun (ano, cod_ibge, vr_pib_mil, vr_pib_per_capita, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    print(f"[contexto-l1] pib ok {len(rows)} linhas")


def _load_comex(conn: psycopg.Connection, ano: int = 2024) -> None:
    n = conn.execute("SELECT count(*) FROM contexto.comex_uf").fetchone()[0]
    if int(n) > 0:
        print(f"[contexto-l1] comex já carregado ({n} linhas)")
        return
    print(f"[contexto-l1] baixando ComexStat UF {ano}…")
    api = "https://api-comexstat.mdic.gov.br/general?language=pt"
    rows = []
    for flow in ("export", "import"):
        body = {
            "flow": flow,
            "monthDetail": False,
            "period": {"from": f"{ano}-01", "to": f"{ano}-12"},
            "filters": [],
            "details": ["state"],
            "metrics": ["metricFOB", "metricKG"],
        }
        payload = json.loads(_post_json(api, body).decode("utf-8"))
        for item in (payload.get("data") or {}).get("list") or []:
            nome = item.get("state") or ""
            sg = UF_NOME.get(_fold(nome))
            if not sg:
                continue
            rows.append(
                (
                    int(item["year"]),
                    sg,
                    nome,
                    flow,
                    float(item.get("metricFOB") or 0),
                    float(item.get("metricKG") or 0),
                    "comexstat_mdic",
                )
            )
    with conn.cursor() as cur:
        with cur.copy(
            "COPY contexto.comex_uf (ano, sg_uf, nm_uf_fonte, fluxo, vr_fob_usd, qt_kg, ds_fonte) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(r)
    print(f"[contexto-l1] comex ok {len(rows)} linhas")


def _patch_catalogo(conn: psycopg.Connection) -> None:
    """Garante pacotes pib/comex no api.catalogo sem reescrever a função inteira."""
    # Inserção via REPLACE da função é frágil; api.pib/comex bastam.
    # Atualiza dicionário se a tabela existir.
    try:
        conn.execute(
            """
            INSERT INTO ref.dicionario_indicador (id_indicador, nome_exato, unidade, schema_tabela, nao_confundir_com, ds_fonte)
            VALUES
              ('vr_pib_mil', 'PIB a preços correntes', 'R$ mil', 'contexto.pib_mun', 'renda familiar; receita municipal', 'IBGE SIDRA 5938'),
              ('vr_pib_per_capita', 'PIB per capita', 'R$', 'contexto.pib_mun', 'renda familiar; salário médio', 'IBGE SIDRA 5938'),
              ('vr_fob_comex', 'Valor FOB comércio exterior', 'USD', 'contexto.comex_uf', 'PIB municipal', 'ComexStat MDIC')
            ON CONFLICT (id_indicador) DO NOTHING
            """
        )
    except Exception as exc:
        print(f"[contexto-l1] dicionario skip: {exc}")


def ensure_contexto_l1() -> None:
    """Chamado no startup do mcp-api (deploy)."""
    global _READY
    if _READY:
        return
    url = _ddl_url()
    if not url:
        print("[contexto-l1] sem DATABASE_URL/ADMIN — skip")
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_file(conn, _SQL_DIR / "patch_pib.sql")
            _run_sql_file(conn, _SQL_DIR / "patch_comex.sql")
            # GRANT extra se role existir
            for stmt in (
                "GRANT EXECUTE ON FUNCTION api.pib(smallint, text, integer, boolean, integer) TO agente",
                "GRANT EXECUTE ON FUNCTION api.comex(smallint, text, text, boolean, integer) TO agente",
                "GRANT SELECT ON contexto.pib_mun TO agente",
                "GRANT SELECT ON contexto.comex_uf TO agente",
            ):
                try:
                    conn.execute(stmt)
                except Exception:
                    pass
            _patch_catalogo(conn)

        # Carga (transação própria)
        with psycopg.connect(url) as conn:
            try:
                _load_pib(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[contexto-l1] carga pib falhou: {exc}")
            try:
                _load_comex(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[contexto-l1] carga comex falhou: {exc}")

        _READY = True
        print("[contexto-l1] ready")
    except Exception as exc:
        print(f"[contexto-l1] ensure falhou: {exc}")
        _READY = False
