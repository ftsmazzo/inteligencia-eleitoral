"""MCP / REST fino: só funções api.* . Sem SQL livre."""
from __future__ import annotations

import html as html_module
import os
import secrets
from pathlib import Path
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Inteligência Eleitoral Brasil", version="0.1")
MSG_AUTH = "não autorizado"
_STATIC = Path(__file__).resolve().parent / "static"
_GUIA = _STATIC / "guia"
_PATCH_TOKENS = Path(__file__).resolve().parent / "sql" / "patch_mcp_tokens.sql"
_TOKENS_READY = False
_SKILL_PLACEHOLDER = "__SKILL_CONTENT__"
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ensure_tokens_table() -> None:
    global _TOKENS_READY
    if _TOKENS_READY or not _PATCH_TOKENS.exists():
        return
    url = _db_url()
    if not url:
        return
    sql = _PATCH_TOKENS.read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql)
    _TOKENS_READY = True


def _extract_token(authorization: str | None, x_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_token:
        return x_token.strip()
    return ""


def _token_ok(authorization: str | None, x_token: str | None) -> None:
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
        ok = conn.execute(
            "SELECT 1 FROM ctl.mcp_token WHERE token = %s AND ativo IS TRUE",
            (got,),
        ).fetchone()
    if not ok:
        raise HTTPException(401, MSG_AUTH)


def db() -> psycopg.Connection:
    url = os.environ.get("AGENTE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(500, "DATABASE_URL ausente")
    return psycopg.connect(url)


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


class ContasIn(BaseModel):
    ano: int
    sq_candidato: int | None = None
    uf: str | None = None
    sg_partido: str | None = None
    cargo: str | None = None
    limite: int = 200


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


def _one(conn: psycopg.Connection, sql: str, args: tuple) -> Any:
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/guia", status_code=302)


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


@app.post("/guia/api/gerar-token")
def guia_gerar_token(body: GerarTokenIn) -> dict[str, str]:
    if os.environ.get("GUIA_EMIT_TOKEN", "true").lower() in ("0", "false", "no"):
        raise HTTPException(403, "Emissão de token desativada")
    _ensure_tokens_table()
    url = _db_url()
    if not url:
        raise HTTPException(503, "Indisponível")
    token = secrets.token_urlsafe(32)
    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO ctl.mcp_token (token, rotulo) VALUES (%s, %s)",
            (token, body.rotulo.strip()),
        )
        conn.commit()
    return {
        "status": "ok",
        "token": token,
        "rotulo": body.rotulo.strip(),
        "aviso": "Copie agora. Este token não será exibido de novo.",
    }


@app.get("/guia/api/skill")
def guia_skill() -> PlainTextResponse:
    return PlainTextResponse(_skill_text(), media_type="text/plain; charset=utf-8", headers=_NO_CACHE)


if _GUIA.is_dir():
    app.mount("/guia/recursos", StaticFiles(directory=_GUIA / "recursos"), name="guia-recursos")


@app.get("/v1/catalogo")
def catalogo(
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
) -> Any:
    _token_ok(authorization, x_token)
    with db() as conn:
        return _one(conn, "SELECT api.catalogo()", ())


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
    with db() as conn:
        return _one(
            conn,
            "SELECT api.despesa(%s,%s,%s,%s,%s,%s)",
            (body.ano, body.sq_candidato, body.uf, body.sg_partido, body.cargo, body.limite),
        )


@app.post("/v1/eleitos")
def eleitos(body: EleitosIn, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
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


class McpCall(BaseModel):
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@app.post("/mcp")
def mcp(body: McpCall, authorization: str | None = Header(default=None), x_token: str | None = Header(default=None)) -> Any:
    _token_ok(authorization, x_token)
    name = body.method
    p = body.params
    if name == "catalogo":
        return catalogo(authorization, x_token)
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
    if name == "receita":
        return receita(ContasIn(**p), authorization, x_token)
    if name == "despesa":
        return despesa(ContasIn(**p), authorization, x_token)
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
    raise HTTPException(400, "tool inexistente neste catálogo")
