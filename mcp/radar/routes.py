"""API HTTP do Radar sob /apura/api/radar — JWT Apura + campanha_id."""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apura.auth import decodificar_jwt, usuario_por_id
from radar import collect as radar_collect
from radar import seed_alvos
from radar import store
from radar.schema import ensure_schema

router = APIRouter(prefix="/apura/api/radar", tags=["radar"])

_SCHEDULER_STARTED = False


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _start_scheduler() -> None:
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if (os.environ.get("RADAR_SCHEDULER") or "1").strip() in ("0", "false", "off"):
        return
    _SCHEDULER_STARTED = True

    def loop() -> None:
        while True:
            try:
                url = _ddl_url()
                if url:

                    @contextmanager
                    def factory() -> Iterator[psycopg.Connection]:
                        with psycopg.connect(url) as conn:
                            yield conn

                    radar_collect.maybe_run_slot(factory)
            except Exception:
                pass
            time.sleep(60)

    t = threading.Thread(target=loop, name="radar-slots", daemon=True)
    t.start()


def _ensure() -> None:
    try:
        ensure_schema()
    except Exception as exc:
        raise HTTPException(503, f"Falha ao preparar Radar ({exc})") from exc
    _start_scheduler()


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
        raise HTTPException(403, "Usuário sem campanha")
    return row


class AlvoIn(BaseModel):
    kind: str = Field(default="pessoa")
    nome: str = Field(min_length=1, max_length=200)
    query_news: str = Field(default="", max_length=300)
    handle_ig: str | None = Field(default=None, max_length=80)
    is_own: bool = False
    ativo: bool = True


class AlvoPatch(BaseModel):
    kind: str | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    query_news: str | None = None
    handle_ig: str | None = None
    is_own: bool | None = None
    ativo: bool | None = None


@router.get("/meta")
def meta(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, cnome = _campanha(user)
    with _db() as conn:
        seed_alvos.ensure_default_alvo(conn, cid, cnome)
        kpi = store.kpi_24h(conn, cid)
        run = store.last_run(conn, cid)
    return {
        "campanha_id": cid,
        "campanha_nome": cnome,
        "kpi": kpi,
        "last_run": run,
        "nivel": "indicio",
    }


@router.get("/stream")
def stream(
    q: str | None = None,
    canal: str | None = None,
    origem: str | None = None,
    tipo: str | None = None,
    urgencia: str | None = None,
    janela_horas: int = 168,
    page: int = 1,
    limite: int = 20,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        return store.stream(
            conn,
            cid,
            q=q,
            canal=canal,
            origem=origem,
            tipo=tipo,
            urgencia=urgencia,
            janela_horas=janela_horas,
            page=page,
            limite=limite,
        )


@router.get("/kpi")
def kpi(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        return {"nivel": "indicio", **store.kpi_24h(conn, cid)}


@router.get("/alvos")
def alvos(user: tuple[str, str, str] = Depends(_usuario)) -> list[dict[str, Any]]:
    cid, cnome = _campanha(user)
    with _db() as conn:
        seed_alvos.ensure_default_alvo(conn, cid, cnome)
        return store.list_alvos(conn, cid, ativo_only=False)


@router.post("/alvos")
def criar_alvo(body: AlvoIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return store.upsert_alvo(
                conn,
                cid,
                kind=body.kind,
                nome=body.nome,
                query_news=body.query_news,
                handle_ig=body.handle_ig,
                is_own=body.is_own,
                ativo=body.ativo,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.patch("/alvos/{alvo_id}")
def patch_alvo(
    alvo_id: str,
    body: AlvoPatch,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        cur = next(
            (a for a in store.list_alvos(conn, cid, ativo_only=False) if a["id"] == alvo_id),
            None,
        )
        if not cur:
            raise HTTPException(404, "Alvo não encontrado")
        try:
            return store.upsert_alvo(
                conn,
                cid,
                kind=body.kind or cur["kind"],
                nome=body.nome or cur["nome"],
                query_news=body.query_news if body.query_news is not None else cur["query_news"],
                handle_ig=body.handle_ig if body.handle_ig is not None else cur["handle_ig"],
                is_own=cur["is_own"] if body.is_own is None else body.is_own,
                ativo=cur["ativo"] if body.ativo is None else body.ativo,
                alvo_id=alvo_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.delete("/alvos/{alvo_id}")
def apagar_alvo(alvo_id: str, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, str]:
    cid, _ = _campanha(user)
    with _db() as conn:
        store.delete_alvo(conn, cid, alvo_id)
    return {"status": "ok"}


@router.post("/alvos/sync-tse")
def sync_tse(ano: int = 2026, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, cnome = _campanha(user)
    with _db() as conn:
        return seed_alvos.sync_tse_redes(conn, cid, cnome, ano=ano)


@router.post("/coletar")
def coletar(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, cnome = _campanha(user)
    with _db() as conn:
        seed_alvos.ensure_default_alvo(conn, cid, cnome)
        result = radar_collect.collect_campanha(conn, cid, mode="manual")
    return {"nivel": "indicio", **result}


@router.get("/runs/last")
def runs_last(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        run = store.last_run(conn, cid)
    return run or {"status": "vazio"}


@router.get("/eixos")
def eixos(user: tuple[str, str, str] = Depends(_usuario)) -> list[dict[str, Any]]:
    cid, _ = _campanha(user)
    with _db() as conn:
        return store.list_eixos(conn, cid)


@router.get("/mix")
def mix(
    janela_horas: int = 168,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        return store.mix_por_eixo(conn, cid, janela_horas=janela_horas)
