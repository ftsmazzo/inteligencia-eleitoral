"""MCP / REST fino: só funções api.* . Sem SQL livre."""
from __future__ import annotations

import html as html_module
import hashlib
import os
import secrets
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from apura.routes import pagina_apura, pagina_cadastro, router as apura_router
from radar.routes import router as radar_router

app = FastAPI(title="Inteligência Eleitoral Brasil", version="0.1")
app.include_router(apura_router)
app.include_router(radar_router)


@app.exception_handler(Exception)
async def apura_erro_generico(_request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if not isinstance(detail, str):
            detail = str(detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


MSG_AUTH = "não autorizado"
_STATIC = Path(__file__).resolve().parent / "static"
_GUIA = _STATIC / "guia"
_LANDING = _STATIC / "landing"
_PATCH_TOKENS = Path(__file__).resolve().parent / "sql" / "patch_mcp_tokens.sql"
_PATCH_PARTIDO = Path(__file__).resolve().parent / "sql" / "patch_partido_linha.sql"
_PATCH_ACERVO = Path(__file__).resolve().parent / "sql" / "patch_acervo.sql"
_PATCH_ANALITICO = Path(__file__).resolve().parent / "sql" / "patch_analitico.sql"
_PATCH_PEDIDO = Path(__file__).resolve().parent / "sql" / "patch_pedido_demo.sql"
_PATCH_CONTAS_RESUMO = Path(__file__).resolve().parent / "sql" / "patch_contas_resumo.sql"
_PATCH_REDE_COMPLEMENTAR = Path(__file__).resolve().parent / "sql" / "patch_rede_complementar_api.sql"
_PATCH_NOMINATA_CARGO = Path(__file__).resolve().parent / "sql" / "patch_nominata_cargo_geral.sql"
_PATCH_MUNICIPIO = Path(__file__).resolve().parent / "sql" / "patch_municipio_api.sql"
_API_SQL = Path(__file__).resolve().parent / "sql" / "api.sql"
_TOKENS_READY = False
_PEDIDO_READY = False
_API_PARTIDO_READY = False
_ACERVO_READY = False
_ANALITICO_READY = False
_CONTAS_RESUMO_READY = False
_REDE_COMPLEMENTAR_READY = False
_SKILL_PLACEHOLDER = "__SKILL_CONTENT__"
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}
_DEMO_QUOTA_DEFAULT = 5
_DEMO_EMAIL_TO = "fredmazzo@gmail.com"


def _demo_quota_mcp() -> int:
    raw = os.environ.get("DEMO_QUOTA", str(_DEMO_QUOTA_DEFAULT)).strip()
    try:
        n = int(raw)
    except ValueError:
        return _DEMO_QUOTA_DEFAULT
    return max(1, min(n, 100))


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _ensure_tokens_table() -> None:
    global _TOKENS_READY
    if _TOKENS_READY or not _PATCH_TOKENS.exists():
        return
    url = _ddl_url()
    if not url:
        return
    sql = _PATCH_TOKENS.read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql)
    _TOKENS_READY = True


def _ensure_pedido_demo() -> None:
    global _PEDIDO_READY
    if _PEDIDO_READY or not _PATCH_PEDIDO.exists():
        return
    url = _ddl_url()
    if not url:
        return
    sql = _PATCH_PEDIDO.read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql)
    _PEDIDO_READY = True


def _demo_destinatario() -> str:
    return (os.environ.get("DEMO_EMAIL_TO") or _DEMO_EMAIL_TO).strip()


def _enviar_email_smtp(assunto: str, corpo: str, reply_to: str) -> bool:
    host = (os.environ.get("SMTP_HOST") or "").strip()
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    if not host or not user or not password:
        return False
    port = int(os.environ.get("SMTP_PORT") or "587")
    destin = _demo_destinatario()
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = user
    msg["To"] = destin
    msg["Reply-To"] = reply_to
    msg.set_content(corpo)
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return True


def _enviar_email_formsubmit(nome: str, email: str, empresa: str, mensagem: str) -> bool:
    destin = _demo_destinatario()
    payload = {
        "name": nome,
        "email": email,
        "empresa": empresa or "(não informado)",
        "message": mensagem or "(sem mensagem)",
        "_subject": f"Apura · Pedido de demo — {nome}",
        "_template": "table",
        "_captcha": "false",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                f"https://formsubmit.co/ajax/{destin}",
                json=payload,
                headers={"Accept": "application/json"},
            )
        return r.status_code < 400
    except Exception:
        return False


def _run_sql_script(conn: psycopg.Connection, text: str) -> None:
    """Executa script SQL multi-statement respeitando blocos $$ ... $$."""
    stmts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in text.splitlines():
        if not in_dollar and line.strip().startswith("--"):
            continue
        # toggle em ocorrências de $$
        parts = line.split("$$")
        if len(parts) > 1:
            # número ímpar de $$ inverte o estado ao final da linha
            if (len(parts) - 1) % 2 == 1:
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


def _ensure_partido_linha() -> None:
    """Aplica linha partidária + funções api.* (siglas/regiões equivalentes)."""
    global _API_PARTIDO_READY
    if _API_PARTIDO_READY:
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            already = conn.execute(
                """
                SELECT count(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'api' AND p.proname = 'siglas_equivalentes'
                """
            ).fetchone()
            if already and int(already[0]) > 0:
                _API_PARTIDO_READY = True
                return
            if _PATCH_PARTIDO.exists():
                _run_sql_script(conn, _PATCH_PARTIDO.read_text(encoding="utf-8"))
            if _API_SQL.exists():
                _run_sql_script(conn, _API_SQL.read_text(encoding="utf-8"))
            for fn in (
                "GRANT EXECUTE ON FUNCTION api.siglas_equivalentes(text) TO agente",
                "GRANT EXECUTE ON FUNCTION api.partido_match(text, text) TO agente",
                "GRANT EXECUTE ON FUNCTION api.ufs_da_regiao(text) TO agente",
                "GRANT EXECUTE ON FUNCTION api.eh_regiao(text) TO agente",
                "GRANT EXECUTE ON FUNCTION api.uf_match(text, text) TO agente",
            ):
                try:
                    conn.execute(fn)
                except psycopg.Error:
                    pass
        _API_PARTIDO_READY = True
    except Exception:
        # Não derruba o serviço se o DDL falhar; consultas sem expansão ainda funcionam.
        _API_PARTIDO_READY = False


def _ensure_contas_resumo() -> None:
    """Totais + categorias de despesa + custo/voto (após api.sql)."""
    global _CONTAS_RESUMO_READY
    if _CONTAS_RESUMO_READY or not _PATCH_CONTAS_RESUMO.exists():
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_CONTAS_RESUMO.read_text(encoding="utf-8"))
        _CONTAS_RESUMO_READY = True
    except Exception:
        _CONTAS_RESUMO_READY = False


def _ensure_rede_complementar() -> None:
    """Redes sociais + informações complementares TSE."""
    global _REDE_COMPLEMENTAR_READY
    if _REDE_COMPLEMENTAR_READY or not _PATCH_REDE_COMPLEMENTAR.exists():
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_REDE_COMPLEMENTAR.read_text(encoding="utf-8"))
        _REDE_COMPLEMENTAR_READY = True
    except Exception:
        _REDE_COMPLEMENTAR_READY = False


_NOMINATA_CARGO_READY = False
_MUNICIPIO_READY = False


def _ensure_nominata_cargo_geral() -> None:
    """Evita falso vazio: cod_ibge em nominata de cargo geral."""
    global _NOMINATA_CARGO_READY
    if _NOMINATA_CARGO_READY or not _PATCH_NOMINATA_CARGO.exists():
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_NOMINATA_CARGO.read_text(encoding="utf-8"))
        _NOMINATA_CARGO_READY = True
    except Exception:
        _NOMINATA_CARGO_READY = False


def _ensure_municipio_api() -> None:
    """api.municipio: nome → cod_ibge."""
    global _MUNICIPIO_READY
    if _MUNICIPIO_READY or not _PATCH_MUNICIPIO.exists():
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_MUNICIPIO.read_text(encoding="utf-8"))
        _MUNICIPIO_READY = True
    except Exception:
        _MUNICIPIO_READY = False


_SEED_DIR = Path(__file__).resolve().parent / "seed"


def _ensure_analitico() -> None:
    global _ANALITICO_READY
    if _ANALITICO_READY or not _PATCH_ANALITICO.exists():
        return
    url = _ddl_url()
    if not url:
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_ANALITICO.read_text(encoding="utf-8"))
            for fn in (
                "GRANT EXECUTE ON FUNCTION api.consultar_acervo_comparar(text, smallint, smallint, text, text, integer) TO agente",
                "GRANT EXECUTE ON FUNCTION api.linha_temporal_eleitos(text, text, text, smallint[], integer) TO agente",
                "GRANT EXECUTE ON FUNCTION api.cruzamento_social_urna(smallint, text, text, smallint, text, integer) TO agente",
                "GRANT EXECUTE ON FUNCTION api.mandato_urna(smallint, text, text, text, integer) TO agente",
            ):
                try:
                    conn.execute(fn)
                except psycopg.Error:
                    pass
        _ANALITICO_READY = True
    except Exception:
        _ANALITICO_READY = False


_SEED_PLANOS = _SEED_DIR / "acervo_planos_2026.jsonl"
_UFS_BR = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)


def _upsert_acervo_doc(conn: psycopg.Connection, doc: dict) -> None:
    import json
    import uuid as _uuid

    dig = doc.get("sha256")
    if not dig:
        return
    row = conn.execute(
        "SELECT id FROM acervo.documento WHERE sha256 = %s AND tipo = %s",
        (dig, doc.get("tipo") or "plano_governo"),
    ).fetchone()
    expected = len([c for c in (doc.get("chunks") or []) if (c.get("texto") or "").strip()])
    if row:
        n = conn.execute(
            "SELECT count(*) FROM acervo.chunk WHERE documento_id = %s",
            (row[0],),
        ).fetchone()[0]
        if n == expected and expected > 0:
            return
        doc_id = row[0]
        conn.execute("DELETE FROM acervo.chunk WHERE documento_id = %s", (doc_id,))
        conn.execute(
            """
            UPDATE acervo.documento SET
              titulo=%s, descricao=%s, nivel=%s, ano_eleicao=%s,
              vigencia_inicio=%s, vigencia_fim=%s, escopo=%s, sg_uf=%s,
              nm_candidato=%s, cargo=%s, tags=%s, fonte_orgao=%s,
              id_base_raw=%s, meta=%s::jsonb, ativo=true, atualizado_em=now()
            WHERE id=%s
            """,
            (
                doc["titulo"],
                doc.get("descricao") or "",
                doc.get("nivel") or "referencia",
                doc.get("ano_eleicao"),
                doc.get("vigencia_inicio"),
                doc.get("vigencia_fim"),
                doc.get("escopo") or "BR",
                doc.get("sg_uf"),
                doc.get("nm_candidato"),
                doc.get("cargo"),
                doc.get("tags") or [],
                doc.get("fonte_orgao"),
                doc.get("id_base_raw"),
                json.dumps(doc.get("meta") or {}, ensure_ascii=False),
                doc_id,
            ),
        )
    else:
        doc_id = _uuid.uuid4()
        conn.execute(
            """
            INSERT INTO acervo.documento (
              id, tipo, titulo, descricao, nivel, ano_eleicao,
              vigencia_inicio, vigencia_fim, escopo, sg_uf, sg_partido,
              nm_candidato, cargo, tags, fonte_orgao, sha256,
              id_base_raw, meta
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
            )
            """,
            (
                doc_id,
                doc.get("tipo") or "plano_governo",
                doc["titulo"],
                doc.get("descricao") or "",
                doc.get("nivel") or "referencia",
                doc.get("ano_eleicao"),
                doc.get("vigencia_inicio"),
                doc.get("vigencia_fim"),
                doc.get("escopo") or "BR",
                doc.get("sg_uf"),
                doc.get("sg_partido"),
                doc.get("nm_candidato"),
                doc.get("cargo"),
                doc.get("tags") or [],
                doc.get("fonte_orgao"),
                dig,
                doc.get("id_base_raw"),
                json.dumps(doc.get("meta") or {}, ensure_ascii=False),
            ),
        )
    for ch in doc.get("chunks") or []:
        texto = (ch.get("texto") or "").strip()
        if not texto:
            continue
        conn.execute(
            """
            INSERT INTO acervo.chunk (documento_id, ord, secao, texto, token_count)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                doc_id,
                int(ch.get("ord") or 0),
                ch.get("secao") or "",
                texto,
                max(1, len(texto) // 4),
            ),
        )


def _texto_ficha_territorial(conn: psycopg.Connection, uf: str, ano: int) -> str:
    municipal = ano in (2016, 2020, 2024)
    cargo_prop = 13 if municipal else 6  # vereador | dep. federal
    cargo_maj = 11 if municipal else 3  # prefeito | governador
    label_prop = "vereador" if municipal else "deputado federal"
    label_maj = "prefeito" if municipal else "governador"
    row = conn.execute(
        """
        SELECT
          count(DISTINCT v.sq_candidato) FILTER (WHERE v.cd_cargo = %s),
          count(DISTINCT v.sq_candidato) FILTER (
            WHERE v.cd_cargo = %s AND api._eh_eleito(v.ds_sit_tot_turno)
          ),
          coalesce(sum(v.qt_votos) FILTER (WHERE v.cd_cargo = %s AND v.nr_turno = 1), 0)::bigint
        FROM eleicao.votacao v
        WHERE v.ano = %s AND v.sg_uf = %s
        """,
        (cargo_prop, cargo_maj, cargo_maj, ano, uf),
    ).fetchone()
    ele = conn.execute(
        """
        SELECT sg_partido, count(*)::int
        FROM (
          SELECT DISTINCT ON (sq_candidato) sq_candidato, sg_partido
          FROM eleicao.votacao
          WHERE ano = %s AND sg_uf = %s AND cd_cargo = %s AND api._eh_eleito(ds_sit_tot_turno)
        ) t
        GROUP BY 1 ORDER BY 2 DESC LIMIT 5
        """,
        (ano, uf, cargo_prop),
    ).fetchall()
    eleitorado = conn.execute(
        "SELECT coalesce(sum(qt_eleitores), 0)::bigint FROM eleicao.eleitorado WHERE ano = %s AND sg_uf = %s",
        (ano, uf),
    ).fetchone()[0]
    linhas = [
        f"# Perfil eleitoral {uf} · urna {ano}",
        "",
        f"Eleitorado cadastrado (perfil TSE, soma municipal): {eleitorado:,} eleitores.",
        f"Candidatos a {label_prop} distintos na urna: {row[0] or 0}.",
        f"{label_maj.capitalize()} eleito (turno registrado, contagem distinta): {row[1] or 0}.",
        f"Votos nominais 1º turno {label_maj} (soma UF): {row[2] or 0:,}.",
        "",
        f"## Top partidos — cadeiras {label_prop}",
    ]
    if ele:
        linhas.extend(f"- {sg}: {n} eleito(s)" for sg, n in ele)
    else:
        linhas.append(f"- (sem eleitos a {label_prop} neste filtro)")
    linhas.extend(
        [
            "",
            "Fonte: Trilha A (eleicao.votacao, eleicao.eleitorado). "
            "Texto derivado — cifras oficiais via api.eleitos/votacao.",
        ]
    )
    return "\n".join(linhas)


def _bootstrap_fichas_territoriais(conn: psycopg.Connection, ano: int = 2022) -> None:
    n = conn.execute(
        "SELECT count(*) FROM acervo.documento WHERE ativo AND tipo = 'ficha_territorial' AND ano_eleicao = %s",
        (ano,),
    ).fetchone()[0]
    if n >= len(_UFS_BR):
        return
    print(f"[acervo] bootstrap fichas territoriais {ano} ({len(_UFS_BR)} UFs)")
    for uf in _UFS_BR:
        body = _texto_ficha_territorial(conn, uf, ano)
        digest = hashlib.sha256(f"ficha_{uf}_{ano}_{body[:200]}".encode()).hexdigest()
        _upsert_acervo_doc(
            conn,
            {
                "tipo": "ficha_territorial",
                "titulo": f"Ficha territorial {uf} · {ano}",
                "descricao": f"Perfil eleitoral derivado da urna {ano} para {uf}.",
                "nivel": "referencia",
                "ano_eleicao": ano,
                "vigencia_inicio": f"{ano}-01-01",
                "vigencia_fim": f"{ano}-12-31",
                "escopo": "UF",
                "sg_uf": uf,
                "tags": ["ficha_territorial", uf, str(ano)],
                "fonte_orgao": "Derivado Trilha A · TSE",
                "sha256": digest,
                "id_base_raw": "acervo_ficha_territorial",
                "meta": {"uf": uf, "ano": ano},
                "chunks": [{"ord": 0, "secao": f"Perfil {uf}", "texto": body}],
            },
        )


def _ensure_acervo() -> None:
    global _ACERVO_READY
    if _ACERVO_READY:
        return
    url = _ddl_url()
    if not url or not _PATCH_ACERVO.exists():
        return
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            _run_sql_script(conn, _PATCH_ACERVO.read_text(encoding="utf-8"))
            try:
                conn.execute(
                    "GRANT EXECUTE ON FUNCTION api.consultar_acervo(text, smallint, text, text, text, date, integer, text) TO agente"
                )
            except psycopg.Error:
                pass
            try:
                conn.execute("GRANT EXECUTE ON FUNCTION api.acervo_norm(text) TO agente")
            except psycopg.Error:
                pass
            try:
                conn.execute(
                    "GRANT EXECUTE ON FUNCTION api.consultar_acervo_comparar(text, smallint, smallint, text, text, integer) TO agente"
                )
            except psycopg.Error:
                pass
            for seed_path in sorted(_SEED_DIR.glob("acervo_*.jsonl")):
                _seed_acervo_file(conn, seed_path)
            _bootstrap_fichas_territoriais(conn, ano=2022)
            _bootstrap_fichas_territoriais(conn, ano=2018)
            _bootstrap_fichas_territoriais(conn, ano=2020)
            _bootstrap_fichas_territoriais(conn, ano=2024)
        _ACERVO_READY = True
    except Exception:
        _ACERVO_READY = False


def _seed_acervo_file(conn: psycopg.Connection, seed_path: Path) -> None:
    """Carga idempotente de um arquivo seed JSONL (sha256 por documento)."""
    import json

    if not seed_path.exists():
        return
    print(f"[acervo] carregando seed {seed_path.name}")
    with seed_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            _upsert_acervo_doc(conn, doc)


@app.on_event("startup")
def _startup_ddl() -> None:
    _ensure_tokens_table()
    _ensure_pedido_demo()
    _ensure_partido_linha()
    _ensure_contas_resumo()
    _ensure_nominata_cargo_geral()
    _ensure_municipio_api()
    _ensure_acervo()
    _ensure_analitico()


def _extract_token(authorization: str | None, x_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_token:
        return x_token.strip()
    return ""


def _token_ok(authorization: str | None, x_token: str | None) -> None:
    """Valida token e consome 1 unidade da cota demo (se houver)."""
    master = os.environ.get("MCP_TOKEN", "")
    got = _extract_token(authorization, x_token)
    if not master and not got:
        return
    if master and got == master:
        return
    if not got:
        raise HTTPException(401, MSG_AUTH)
    _ensure_tokens_table()
    url = _db_url()
    if not url:
        raise HTTPException(401, MSG_AUTH)
    with psycopg.connect(url) as conn:
        row = conn.execute(
            """
            SELECT ativo, quota_max, quota_used
            FROM ctl.mcp_token
            WHERE token = %s
            FOR UPDATE
            """,
            (got,),
        ).fetchone()
        if not row or not row[0]:
            raise HTTPException(401, MSG_AUTH)
        qmax, used = row[1], int(row[2] or 0)
        if qmax is not None and used >= int(qmax):
            raise HTTPException(
                429,
                f"Cota demo esgotada ({qmax} consultas MCP). Gere outro token ou solicite acesso comercial.",
            )
        if qmax is not None:
            conn.execute(
                "UPDATE ctl.mcp_token SET quota_used = quota_used + 1 WHERE token = %s",
                (got,),
            )
        conn.commit()


def db() -> psycopg.Connection:
    url = os.environ.get("AGENTE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(500, "DATABASE_URL ausente")
    return psycopg.connect(url)


class MunicipioIn(BaseModel):
    nome: str
    uf: str | None = None
    limite: int = 10


class NominataIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    sg_partido: str | None = None
    sq_candidato: int | None = None
    nr_candidato: int | None = None
    nm_urna: str | None = None
    limite: int = 200


class VotacaoIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False
    turno: int = 1
    sg_partido: str | None = None
    sq_candidato: int | None = None
    nr_candidato: int | None = None
    nm_urna: str | None = None
    base_pct: str | None = Field(default=None, description="validos ou soma_dois")
    limite: int = 100


class ComparecimentoIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False
    turno: int = 1


class EleitoradoIn(BaseModel):
    ano: int
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False


class ColigacaoIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    sg_partido: str | None = None
    sq_coligacao: int | None = None
    limite: int = 200


class VagasIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    limite: int = 200


class BemIn(BaseModel):
    ano: int
    sq_candidato: int
    limite: int = 200


class RedeSocialIn(BaseModel):
    ano: int
    sq_candidato: int
    limite: int = 50


class ComplementarIn(BaseModel):
    ano: int
    sq_candidato: int


class ContasIn(BaseModel):
    ano: int
    sq_candidato: int | None = None
    uf: str | None = None
    sg_partido: str | None = None
    cargo: str | None = None
    limite: int = 200
    categoria: str | None = None


class ContasResumoIn(BaseModel):
    ano: int
    sq_candidato: int | None = None
    uf: str | None = None
    sg_partido: str | None = None
    cargo: str | None = None
    limite: int = 30
    incluir_votos: bool = True


class EleitosIn(BaseModel):
    ano: int
    cargo: str
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False
    sg_partido: str | None = None
    limite: int = 200


class PopulacaoIn(BaseModel):
    ano: int
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False
    limite: int = 200


class SocialIn(BaseModel):
    anomes: int | None = None
    uf: str | None = None
    cod_ibge: int | None = None
    nacional: bool = False
    limite: int = 200


class DeputadosCasaIn(BaseModel):
    uf: str | None = None
    sg_partido: str | None = None
    nome: str | None = None
    id_deputado: int | None = None
    limite: int = 200


class SenadoresIn(BaseModel):
    uf: str | None = None
    sg_partido: str | None = None
    nome: str | None = None
    id_senador: int | None = None
    limite: int = 200


class ProposicoesIn(BaseModel):
    ano: int
    sigla_tipo: str | None = None
    id_deputado: int | None = None
    limite: int = 100


class VotosCamaraIn(BaseModel):
    ano: int | None = None
    id_deputado: int | None = None
    uf: str | None = None
    limite: int = 100


class DeparaParlamentarIn(BaseModel):
    casa: str | None = None
    ano_eleicao: int = 2022
    uf: str | None = None
    limite: int = 200


class AcervoIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    ano_eleicao: int | None = None
    tipo: str | None = None
    uf: str | None = None
    sg_partido: str | None = None
    vigente_em: str | None = None
    limite: int = 8
    nm_candidato: str | None = None


class AcervoCompararIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    ano_a: int
    ano_b: int
    tipo: str | None = "plano_governo"
    nm_candidato: str | None = None
    limite: int = 5


class LinhaTemporalIn(BaseModel):
    cargo: str
    sg_partido: str
    uf: str | None = None
    anos: list[int] | None = None
    limite: int = 200


class CruzamentoSocialIn(BaseModel):
    ano_urna: int
    cargo: str
    indicador: str = "cadunico"
    anomes: int | None = None
    uf: str
    top_n: int = 15


class MandatoUrnaIn(BaseModel):
    ano_eleicao: int = 2022
    uf: str | None = None
    sg_partido: str | None = None
    tema: str | None = None
    limite: int = 30


class ClimaIn(BaseModel):
    """Consulta livre ao Radar — alvo/tema sob demanda, sem candidatura travada."""

    q: str | None = Field(default=None, max_length=200, description="Alvo/tema: Flávio, Lula, segurança…")
    canal: str | None = Field(default=None, description="instagram|news|x|facebook|youtube|tiktok|site")
    origem: str | None = Field(default=None, description="clima|oficial")
    tipo: str | None = Field(default=None, description="ataque|defesa|oportunidade|rotina|…")
    urgencia: str | None = None
    janela_horas: int | None = Field(default=168, description="24=dia, 168=semana")
    campaign_id: int | None = Field(default=None, description="Legado: id numérico do painel kxryyk")
    campanha_id: str | None = Field(
        default=None,
        description="UUID ctl.campanha — prioriza store Radar em inteligencia-dados",
    )
    page: int = 1
    limite: int = 20


def _campanha_id_do_token(authorization: str | None, x_token: str | None) -> str | None:
    got = _extract_token(authorization, x_token)
    master = os.environ.get("MCP_TOKEN", "")
    if not got or (master and got == master):
        return None
    url = _db_url()
    if not url:
        return None
    try:
        with psycopg.connect(url) as conn:
            row = conn.execute(
                """
                SELECT campanha_id::text
                FROM ctl.mcp_token
                WHERE token = %s AND ativo IS TRUE
                """,
                (got,),
            ).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _one(conn: psycopg.Connection, sql: str, args: tuple) -> Any:
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


@app.get("/health")
def health() -> dict[str, Any]:
    _ensure_tokens_table()
    _ensure_partido_linha()
    _ensure_contas_resumo()
    _ensure_rede_complementar()
    _ensure_acervo()
    _ensure_analitico()
    out: dict[str, Any] = {
        "status": "ok",
        "partido_linha": "ready" if _API_PARTIDO_READY else "pending",
        "contas_resumo": "ready" if _CONTAS_RESUMO_READY else "pending",
        "rede_complementar": "ready" if _REDE_COMPLEMENTAR_READY else "pending",
        "acervo": "ready" if _ACERVO_READY else "pending",
        "analitico": "ready" if _ANALITICO_READY else "pending",
        "seed_planos": _SEED_PLANOS.exists(),
    }
    url = _ddl_url()
    if url and _ACERVO_READY:
        try:
            with psycopg.connect(url) as conn:
                n_doc = conn.execute("SELECT count(*) FROM acervo.documento WHERE ativo").fetchone()[0]
                n_chunk = conn.execute("SELECT count(*) FROM acervo.chunk").fetchone()[0]
                n_ficha = conn.execute(
                    "SELECT count(*) FROM acervo.documento WHERE ativo AND tipo = 'ficha_territorial'"
                ).fetchone()[0]
                out["acervo_docs"] = int(n_doc)
                out["acervo_chunks"] = int(n_chunk)
                out["acervo_fichas"] = int(n_ficha)
                out["db_date"] = str(conn.execute("SELECT CURRENT_DATE").fetchone()[0])
        except Exception as e:
            out["acervo_stats_erro"] = type(e).__name__
    return out


@app.get("/")
def root() -> HTMLResponse:
    html = (_LANDING / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, media_type="text/html; charset=utf-8", headers=_NO_CACHE)


def _skill_text() -> str:
    path = _GUIA / "recursos" / "skill-ia.md"
    if not path.exists():
        return "Skill indisponível. Baixe skill-ia.md nos links acima."
    return path.read_text(encoding="utf-8")


@app.get("/guia")
def guia() -> HTMLResponse:
    html = (_GUIA / "index.html").read_text(encoding="utf-8")
    skill = html_module.escape(_skill_text(), quote=False)
    html = html.replace(_SKILL_PLACEHOLDER, skill)
    return HTMLResponse(html, media_type="text/html; charset=utf-8", headers=_NO_CACHE)


class GerarTokenIn(BaseModel):
    rotulo: str = Field(min_length=2, max_length=80)


class PedidoDemoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    email: EmailStr
    empresa: str = Field(default="", max_length=120)
    mensagem: str = Field(default="", max_length=1000)


@app.post("/api/pedido-demo")
def pedido_demo(body: PedidoDemoIn) -> dict[str, str]:
    """Recebe formulário da landing, grava no banco e envia e-mail."""
    _ensure_pedido_demo()
    nome = body.nome.strip()
    email = str(body.email).strip().lower()
    empresa = (body.empresa or "").strip()
    mensagem = (body.mensagem or "").strip()
    url = _db_url()
    if url:
        try:
            with psycopg.connect(url) as conn:
                conn.execute(
                    """
                    INSERT INTO ctl.pedido_demo (nome, email, empresa, mensagem)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (nome, email, empresa, mensagem),
                )
                conn.commit()
        except Exception:
            pass

    assunto = f"Apura · Pedido de demo — {nome}"
    corpo = (
        f"Novo pedido de demo (landing)\n\n"
        f"Nome: {nome}\n"
        f"E-mail: {email}\n"
        f"Empresa/campanha: {empresa or '(não informado)'}\n\n"
        f"Mensagem:\n{mensagem or '(sem mensagem)'}\n"
    )
    enviado = False
    try:
        enviado = _enviar_email_smtp(assunto, corpo, email)
    except Exception:
        enviado = False
    if not enviado:
        enviado = _enviar_email_formsubmit(nome, email, empresa, mensagem)

    if not enviado and not url:
        raise HTTPException(503, "Não foi possível registrar o pedido agora. Use o WhatsApp.")

    return {
        "status": "ok",
        "mensagem": (
            "Pedido enviado! Entramos em contato em breve."
            if enviado
            else "Pedido registrado. Se preferir, fale agora no WhatsApp."
        ),
    }


@app.post("/guia/api/gerar-token")
def guia_gerar_token(body: GerarTokenIn) -> dict[str, str]:
    if os.environ.get("GUIA_EMIT_TOKEN", "true").lower() in ("0", "false", "no"):
        raise HTTPException(403, "Emissão de token desativada")
    _ensure_tokens_table()
    url = _db_url()
    if not url:
        raise HTTPException(503, "Indisponível")
    token = secrets.token_urlsafe(32)
    quota = _demo_quota_mcp()
    with psycopg.connect(url) as conn:
        conn.execute(
            """
            INSERT INTO ctl.mcp_token (token, rotulo, quota_max, quota_used)
            VALUES (%s, %s, %s, 0)
            """,
            (token, body.rotulo.strip(), quota),
        )
        conn.commit()
    return {
        "status": "ok",
        "token": token,
        "rotulo": body.rotulo.strip(),
        "quota_max": str(quota),
        "aviso": (
            f"Token demo · {quota} consultas MCP. "
            "Copie agora — não será exibido de novo. "
            "Quando esgotar, solicite acesso comercial."
        ),
    }


@app.get("/guia/api/skill")
def guia_skill() -> PlainTextResponse:
    return PlainTextResponse(_skill_text(), media_type="text/plain; charset=utf-8", headers=_NO_CACHE)


if _GUIA.is_dir():
    app.mount("/guia/recursos", StaticFiles(directory=_GUIA / "recursos"), name="guia-recursos")

_APURA_ASSETS = _STATIC / "apura" / "assets"
if _APURA_ASSETS.is_dir():
    app.mount("/apura/assets", StaticFiles(directory=_APURA_ASSETS), name="apura-assets")

_LANDING_ASSETS = _STATIC / "landing" / "assets"
if _LANDING_ASSETS.is_dir():
    app.mount("/landing/assets", StaticFiles(directory=_LANDING_ASSETS), name="landing-assets")


@app.get("/apura")
def apura() -> RedirectResponse:
    """Acesso público ao chat fica sob contato — redireciona para o formulário."""
    return RedirectResponse(url="/#demo", status_code=302)


@app.get("/apura/app")
def apura_interno() -> HTMLResponse:
    """Acesso interno (conta já existente). Não linkado na landing."""
    return pagina_apura()


@app.get("/apura/cadastro")
def apura_cadastro() -> HTMLResponse:
    """Formulário de solicitação de cadastro (auto-aprovação)."""
    return pagina_cadastro()


@app.get("/v1/catalogo")
def catalogo(
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(conn, "SELECT api.catalogo()", ())


@app.post("/v1/municipio")
def municipio(
    body: MunicipioIn,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
) -> Any:
    _token_ok(authorization, x_token)
    _ensure_municipio_api()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.municipio(%s,%s,%s)",
            (body.nome, body.uf, body.limite),
        )


@app.post("/v1/nominata")
def nominata(body: NominataIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.nominata(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                body.ano,
                body.cargo,
                body.uf,
                body.cod_ibge,
                body.sg_partido,
                body.sq_candidato,
                body.nr_candidato,
                body.nm_urna,
                body.limite,
            ),
        )


@app.post("/v1/votacao")
def votacao(body: VotacaoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.votacao(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                body.ano,
                body.cargo,
                body.uf,
                body.cod_ibge,
                body.nacional,
                body.turno,
                body.sg_partido,
                body.sq_candidato,
                body.nr_candidato,
                body.nm_urna,
                body.base_pct,
                body.limite,
            ),
        )


@app.post("/v1/comparecimento")
def comparecimento(body: ComparecimentoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.comparecimento(%s,%s,%s,%s,%s,%s)",
            (body.ano, body.cargo, body.uf, body.cod_ibge, body.nacional, body.turno),
        )


@app.post("/v1/eleitorado")
def eleitorado(body: EleitoradoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.eleitorado(%s,%s,%s,%s)",
            (body.ano, body.uf, body.cod_ibge, body.nacional),
        )


@app.post("/v1/coligacao")
def coligacao(body: ColigacaoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.coligacao(%s,%s,%s,%s,%s,%s,%s)",
            (
                body.ano,
                body.cargo,
                body.uf,
                body.cod_ibge,
                body.sg_partido,
                body.sq_coligacao,
                body.limite,
            ),
        )


@app.post("/v1/vagas")
def vagas(body: VagasIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.vagas(%s,%s,%s,%s,%s)",
            (body.ano, body.cargo, body.uf, body.cod_ibge, body.limite),
        )


@app.post("/v1/bem")
def bem(body: BemIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.bem(%s,%s,%s)",
            (body.ano, body.sq_candidato, body.limite),
        )


@app.post("/v1/rede_social")
def rede_social(
    body: RedeSocialIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)
) -> Any:
    _token_ok(authorization, x_token)
    _ensure_rede_complementar()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.rede_social(%s,%s,%s)",
            (body.ano, body.sq_candidato, body.limite),
        )


@app.post("/v1/complementar")
def complementar(
    body: ComplementarIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)
) -> Any:
    _token_ok(authorization, x_token)
    _ensure_rede_complementar()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.complementar(%s,%s)",
            (body.ano, body.sq_candidato),
        )


@app.post("/v1/receita")
def receita(body: ContasIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.receita(%s,%s,%s,%s,%s,%s)",
            (body.ano, body.sq_candidato, body.uf, body.sg_partido, body.cargo, body.limite),
        )


@app.post("/v1/despesa")
def despesa(body: ContasIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_contas_resumo()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.despesa(%s,%s,%s,%s,%s,%s,%s)",
            (body.ano, body.sq_candidato, body.uf, body.sg_partido, body.cargo, body.limite, body.categoria),
        )


@app.post("/v1/contas_resumo")
def contas_resumo(
    body: ContasResumoIn,
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
) -> Any:
    _token_ok(authorization, x_token)
    _ensure_contas_resumo()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.contas_resumo(%s,%s,%s,%s,%s,%s,%s)",
            (
                body.ano,
                body.uf,
                body.cargo,
                body.sg_partido,
                body.sq_candidato,
                body.limite,
                body.incluir_votos,
            ),
        )


@app.post("/v1/eleitos")
def eleitos(body: EleitosIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_partido_linha()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.eleitos(%s,%s,%s,%s,%s,%s,%s)",
            (
                body.ano,
                body.cargo,
                body.uf,
                body.cod_ibge,
                body.nacional,
                body.sg_partido,
                body.limite,
            ),
        )


@app.post("/v1/populacao")
def populacao(body: PopulacaoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.populacao(%s,%s,%s,%s,%s)",
            (body.ano, body.uf, body.cod_ibge, body.nacional, body.limite),
        )


@app.post("/v1/cadunico")
def cadunico(body: SocialIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.cadunico(%s,%s,%s,%s,%s)",
            (body.anomes, body.uf, body.cod_ibge, body.nacional, body.limite),
        )


@app.post("/v1/bolsa_familia")
def bolsa_familia(body: SocialIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.bolsa_familia(%s,%s,%s,%s,%s)",
            (body.anomes, body.uf, body.cod_ibge, body.nacional, body.limite),
        )


@app.post("/v1/deputados_casa")
def deputados_casa(body: DeputadosCasaIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.deputados_casa(%s,%s,%s,%s,%s)",
            (body.uf, body.sg_partido, body.nome, body.id_deputado, body.limite),
        )


@app.post("/v1/senadores")
def senadores(body: SenadoresIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.senadores(%s,%s,%s,%s,%s)",
            (body.uf, body.sg_partido, body.nome, body.id_senador, body.limite),
        )


@app.post("/v1/proposicoes")
def proposicoes(body: ProposicoesIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.proposicoes(%s,%s,%s,%s)",
            (body.ano, body.sigla_tipo, body.id_deputado, body.limite),
        )


@app.post("/v1/votos_camara")
def votos_camara(body: VotosCamaraIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.votos_camara(%s,%s,%s,%s)",
            (body.ano, body.id_deputado, body.uf, body.limite),
        )


@app.post("/v1/depara_parlamentar")
def depara_parlamentar(body: DeparaParlamentarIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(
            conn,
            "SELECT api.depara_parlamentar(%s,%s,%s,%s)",
            (body.casa, body.ano_eleicao, body.uf, body.limite),
        )


@app.post("/v1/acervo")
def acervo(body: AcervoIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_acervo()
    # NULL explícito em p_vigente_em anula DEFAULT CURRENT_DATE — sempre passar data concreta.
    vigente = body.vigente_em or date.today().isoformat()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.consultar_acervo(%s,%s,%s,%s,%s,%s::date,%s,%s)",
            (
                body.query,
                body.ano_eleicao,
                body.tipo,
                body.uf,
                body.sg_partido,
                vigente,
                body.limite,
                body.nm_candidato,
            ),
        )


@app.post("/v1/acervo_comparar")
def acervo_comparar(body: AcervoCompararIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_acervo()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.consultar_acervo_comparar(%s,%s,%s,%s,%s,%s)",
            (body.query, body.ano_a, body.ano_b, body.tipo, body.nm_candidato, body.limite),
        )


@app.post("/v1/linha_temporal")
def linha_temporal(body: LinhaTemporalIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_analitico()
    _ensure_partido_linha()
    anos = body.anos or [2014, 2018, 2022]
    with db() as conn:
        return _one(
            conn,
            "SELECT api.linha_temporal_eleitos(%s,%s,%s,%s::smallint[],%s)",
            (body.cargo, body.sg_partido, body.uf, anos, body.limite),
        )


@app.post("/v1/cruzamento_social")
def cruzamento_social(body: CruzamentoSocialIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_analitico()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.cruzamento_social_urna(%s,%s,%s,%s,%s,%s)",
            (body.ano_urna, body.cargo, body.indicador, body.anomes, body.uf, body.top_n),
        )


@app.post("/v1/mandato_urna")
def mandato_urna(body: MandatoUrnaIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    _ensure_analitico()
    with db() as conn:
        return _one(
            conn,
            "SELECT api.mandato_urna(%s,%s,%s,%s,%s)",
            (body.ano_eleicao, body.uf, body.sg_partido, body.tema, body.limite),
        )


@app.post("/v1/clima")
async def clima(body: ClimaIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    from radar_client import consultar_clima

    campanha_uuid = (body.campanha_id or "").strip() or _campanha_id_do_token(authorization, x_token)
    return await consultar_clima(
        q=body.q,
        canal=body.canal,
        origem=body.origem,
        tipo=body.tipo,
        urgencia=body.urgencia,
        janela_horas=body.janela_horas,
        campaign_id=body.campaign_id,
        campanha_id=campanha_uuid,
        page=body.page,
        limite=body.limite,
    )


class McpCall(BaseModel):
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@app.post("/mcp")
async def mcp(body: McpCall, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    name = body.method
    p = body.params
    if name == "catalogo":
        return catalogo(authorization, x_token)
    if name == "municipio":
        return municipio(MunicipioIn(**p), authorization, x_token)
    if name == "nominata":
        return nominata(NominataIn(**p), authorization, x_token)
    if name == "votacao":
        return votacao(VotacaoIn(**p), authorization, x_token)
    if name == "comparecimento":
        return comparecimento(ComparecimentoIn(**p), authorization, x_token)
    if name == "eleitorado":
        return eleitorado(EleitoradoIn(**p), authorization, x_token)
    if name == "coligacao":
        return coligacao(ColigacaoIn(**p), authorization, x_token)
    if name == "vagas":
        return vagas(VagasIn(**p), authorization, x_token)
    if name == "bem":
        return bem(BemIn(**p), authorization, x_token)
    if name == "rede_social":
        return rede_social(RedeSocialIn(**p), authorization, x_token)
    if name == "complementar":
        return complementar(ComplementarIn(**p), authorization, x_token)
    if name == "receita":
        return receita(ContasIn(**p), authorization, x_token)
    if name == "despesa":
        return despesa(ContasIn(**p), authorization, x_token)
    if name == "contas_resumo":
        return contas_resumo(ContasResumoIn(**p), authorization, x_token)
    if name == "eleitos":
        return eleitos(EleitosIn(**p), authorization, x_token)
    if name == "populacao":
        return populacao(PopulacaoIn(**p), authorization, x_token)
    if name == "cadunico":
        return cadunico(SocialIn(**p), authorization, x_token)
    if name == "bolsa_familia":
        return bolsa_familia(SocialIn(**p), authorization, x_token)
    if name == "deputados_casa":
        return deputados_casa(DeputadosCasaIn(**p), authorization, x_token)
    if name == "senadores":
        return senadores(SenadoresIn(**p), authorization, x_token)
    if name == "proposicoes":
        return proposicoes(ProposicoesIn(**p), authorization, x_token)
    if name == "votos_camara":
        return votos_camara(VotosCamaraIn(**p), authorization, x_token)
    if name == "depara_parlamentar":
        return depara_parlamentar(DeparaParlamentarIn(**p), authorization, x_token)
    if name == "acervo":
        return acervo(AcervoIn(**p), authorization, x_token)
    if name == "acervo_comparar":
        return acervo_comparar(AcervoCompararIn(**p), authorization, x_token)
    if name == "linha_temporal":
        return linha_temporal(LinhaTemporalIn(**p), authorization, x_token)
    if name == "cruzamento_social":
        return cruzamento_social(CruzamentoSocialIn(**p), authorization, x_token)
    if name == "mandato_urna":
        return mandato_urna(MandatoUrnaIn(**p), authorization, x_token)
    if name == "clima":
        return await clima(ClimaIn(**p), authorization, x_token)
    raise HTTPException(400, "tool inexistente neste catálogo")
