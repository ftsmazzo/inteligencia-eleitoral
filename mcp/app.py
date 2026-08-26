"""MCP / REST fino: só funções api.* . Sem SQL livre."""
from __future__ import annotations

import os
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Inteligência Eleitoral Brasil", version="0.1")
MSG_AUTH = "não autorizado"


def _token_ok(authorization: str | None, x_token: str | None) -> None:
    expected = os.environ.get("MCP_TOKEN", "")
    if not expected:
        return
    got = ""
    if authorization and authorization.lower().startswith("bearer "):
        got = authorization[7:].strip()
    elif x_token:
        got = x_token
    if got != expected:
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


def _one(conn: psycopg.Connection, sql: str, args: tuple) -> Any:
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    raise HTTPException(400, "tool inexistente neste catálogo")
