"""API HTTP do Mapa sob /apura/api/mapa — JWT + campanha ativa."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import httpx
import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apura.auth import decodificar_jwt, usuario_por_id
from mapa import store
from mapa.schema import ensure_schema

router = APIRouter(prefix="/apura/api/mapa", tags=["mapa"])


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _ensure() -> None:
    try:
        ensure_schema()
    except Exception as exc:
        # Mensagem limpa; deadlock raro após advisory lock + retry
        raise HTTPException(503, f"Falha ao preparar Mapa ({exc})") from exc


@contextmanager
def _db() -> Iterator[psycopg.Connection]:
    _ensure()
    url = _ddl_url() or _db_url()
    if not url:
        raise HTTPException(503, "Banco indisponível")
    with psycopg.connect(url) as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticação necessária")
    return authorization[7:].strip()


def _usuario(authorization: str | None = Header(default=None)) -> tuple[str, str, str]:
    payload = decodificar_jwt(_bearer(authorization))
    with _db() as conn:
        return usuario_por_id(conn, payload["sub"])


def _campanha(user: tuple[str, str, str]) -> tuple[str, str]:
    with _db() as conn:
        row = store.campanha_do_usuario(conn, user[0])
    if not row:
        raise HTTPException(403, "Usuário sem campanha — Operar uma campanha primeiro")
    return row


class NotaIn(BaseModel):
    texto: str = Field(default="", max_length=20000)


class PontoIn(BaseModel):
    cod_ibge: int | None = None
    nome: str | None = None
    lat: float
    lng: float
    ordem: int = 0


class CaravanaIn(BaseModel):
    nome: str = Field(default="Carreata", max_length=200)
    pontos: list[PontoIn] = Field(default_factory=list)
    calcular_rota: bool = True


class CaravanaPatch(BaseModel):
    nome: str | None = Field(default=None, max_length=200)
    pontos: list[PontoIn] | None = None
    calcular_rota: bool = True


async def _rota_osrm(pontos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Rota rodoviária via OSRM público; None se falhar (UI usa linha reta)."""
    if len(pontos) < 2:
        return None
    coords = ";".join(f"{p['lng']},{p['lat']}" for p in pontos)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(url, params={"overview": "full", "geometries": "geojson"})
        if r.status_code >= 400:
            return None
        data = r.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        geom = routes[0].get("geometry")
        return {
            "type": "Feature",
            "properties": {
                "distance_m": routes[0].get("distance"),
                "duration_s": routes[0].get("duration"),
                "fonte": "osrm",
            },
            "geometry": geom,
        }
    except Exception:
        return None


@router.get("/municipios")
def municipios(
    uf: str = "AP",
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    _campanha(user)
    with _db() as conn:
        linhas = store.listar_municipios(conn, uf=uf)
    return {"status": "ok", "uf": (uf or "AP").upper()[:2], "linhas": linhas}


@router.get("/notas")
def notas(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        return {"status": "ok", "linhas": store.listar_notas(conn, camp[0])}


@router.put("/notas/{cod_ibge}")
def salvar_nota(
    cod_ibge: int,
    body: NotaIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        item = store.upsert_nota(
            conn,
            campanha_id=camp[0],
            cod_ibge=cod_ibge,
            texto=body.texto,
            usuario_id=user[0],
        )
    return {"status": "ok", "item": item}


@router.delete("/notas/{cod_ibge}")
def delete_nota(
    cod_ibge: int,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        ok = store.apagar_nota(conn, campanha_id=camp[0], cod_ibge=cod_ibge)
    if not ok:
        raise HTTPException(404, "Nota não encontrada")
    return {"status": "ok"}


@router.get("/caravanas")
def caravanas(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        return {"status": "ok", "linhas": store.listar_caravanas(conn, camp[0])}


@router.post("/caravanas")
async def criar_caravana(
    body: CaravanaIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    pontos = [p.model_dump() for p in body.pontos]
    for i, p in enumerate(pontos):
        p["ordem"] = p.get("ordem") if p.get("ordem") is not None else i
    pontos.sort(key=lambda x: int(x.get("ordem") or 0))
    rota = await _rota_osrm(pontos) if body.calcular_rota else None
    with _db() as conn:
        item = store.salvar_caravana(
            conn,
            campanha_id=camp[0],
            nome=body.nome,
            pontos=pontos,
            rota_geojson=rota,
            usuario_id=user[0],
        )
    return {"status": "ok", "item": item}


@router.patch("/caravanas/{caravana_id}")
async def patch_caravana(
    caravana_id: str,
    body: CaravanaPatch,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        atuais = store.listar_caravanas(conn, camp[0])
        found = next((c for c in atuais if c["id"] == caravana_id), None)
        if not found:
            raise HTTPException(404, "Caravana não encontrada")
        nome = body.nome if body.nome is not None else found["nome"]
        pontos = (
            [p.model_dump() for p in body.pontos]
            if body.pontos is not None
            else found["pontos"]
        )
        for i, p in enumerate(pontos):
            p["ordem"] = p.get("ordem") if p.get("ordem") is not None else i
        pontos.sort(key=lambda x: int(x.get("ordem") or 0))
        rota = found.get("rota_geojson")
        if body.calcular_rota and body.pontos is not None:
            rota = await _rota_osrm(pontos)
        try:
            item = store.salvar_caravana(
                conn,
                campanha_id=camp[0],
                nome=nome,
                pontos=pontos,
                rota_geojson=rota,
                usuario_id=user[0],
                caravana_id=caravana_id,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
    return {"status": "ok", "item": item}


@router.delete("/caravanas/{caravana_id}")
def delete_caravana(
    caravana_id: str,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        ok = store.apagar_caravana(conn, campanha_id=camp[0], caravana_id=caravana_id)
    if not ok:
        raise HTTPException(404, "Caravana não encontrada")
    return {"status": "ok"}
