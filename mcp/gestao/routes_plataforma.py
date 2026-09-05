"""API Plataforma Gestão — /apura/api/gestao/plataforma/*

Frota, criar/entrar campanha, membros, Perfis, tokens MCP, eventos.
Contrato: docs/CONTRATO-PLATAFORMA-GESTAO.md
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apura.auth import decodificar_jwt, usuario_por_id
from gestao import plataforma
from gestao.schema import ensure_schema

router = APIRouter(prefix="/apura/api/gestao/plataforma", tags=["gestao-plataforma"])


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _ensure() -> None:
    try:
        ensure_schema()
    except Exception as exc:
        raise HTTPException(503, f"Falha ao preparar Gestão ({exc})") from exc


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


class CriarCampanhaIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    rotulo: str | None = Field(default=None, max_length=120)


class EntrarIn(BaseModel):
    campanha_id: str = Field(min_length=32, max_length=40)


class MembroIn(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    perfil: str = Field(min_length=2, max_length=80, description="slug ou uuid do perfil")
    papel_campanha: str = Field(default="equipe", description="coordenador|equipe")
    nome: str | None = Field(default=None, max_length=120)


class PerfilPatchIn(BaseModel):
    nome: str | None = Field(default=None, max_length=80)
    descricao: str | None = Field(default=None, max_length=500)
    modelo_orquestrador: str | None = Field(default=None, max_length=120)
    modelo_redator: str | None = Field(default=None, max_length=120)
    quota_perguntas_max: int | None = None
    tools: list[str] | None = None
    ativo: bool | None = None


class TokenIn(BaseModel):
    perfil: str = Field(min_length=2, max_length=80)
    rotulo: str = Field(min_length=2, max_length=120)
    nome: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    quota_max: int | None = None


@router.get("/eu")
def eu(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        return plataforma.contexto_usuario(conn, user[0], user[1])


@router.get("/campanhas")
def campanhas(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        itens = plataforma.listar_campanhas(conn, user[0], user[1])
        return {
            "itens": itens,
            "total": len(itens),
            "is_super_gestor": plataforma.eh_super_gestor(conn, user[1]),
        }


@router.post("/campanhas")
def criar_campanha(
    body: CriarCampanhaIn, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    with _db() as conn:
        try:
            return plataforma.criar_campanha(
                conn,
                usuario_id=user[0],
                email=user[1],
                nome=body.nome,
                rotulo=body.rotulo,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/campanhas/{campanha_id}")
def detalhe(
    campanha_id: str, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    with _db() as conn:
        if not plataforma.eh_super_gestor(conn, user[1]):
            if not plataforma.membro_ativo(conn, user[0], campanha_id):
                raise HTTPException(403, "Sem acesso a esta campanha")
        return plataforma.detalhe_campanha(conn, campanha_id)


@router.post("/entrar")
def entrar(body: EntrarIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        return plataforma.entrar_campanha(
            conn, usuario_id=user[0], email=user[1], campanha_id=body.campanha_id
        )


@router.post("/sair")
def sair(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        return plataforma.sair_campanha_ativa(conn, usuario_id=user[0], email=user[1])


@router.get("/campanhas/{campanha_id}/membros")
def membros(
    campanha_id: str, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_gerir_campanha(conn, user[0], user[1], campanha_id)
        itens = plataforma.listar_membros(conn, campanha_id)
        return {"itens": itens, "total": len(itens)}


@router.post("/campanhas/{campanha_id}/membros")
def upsert_membro(
    campanha_id: str,
    body: MembroIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_gerir_campanha(conn, user[0], user[1], campanha_id)
        try:
            return plataforma.upsert_membro(
                conn,
                campanha_id=campanha_id,
                email=body.email,
                perfil=body.perfil,
                papel_campanha=body.papel_campanha,
                nome=body.nome,
                actor_id=user[0],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.delete("/campanhas/{campanha_id}/membros/{membro_id}")
def desativar_membro(
    campanha_id: str,
    membro_id: str,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_gerir_campanha(conn, user[0], user[1], campanha_id)
        return plataforma.desativar_membro(
            conn, campanha_id=campanha_id, membro_id=membro_id, actor_id=user[0]
        )


@router.get("/perfis")
def perfis(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        # leitura: qualquer autenticado (precisa ver slugs ao atribuir)
        itens = plataforma.listar_perfis(conn)
        return {"itens": itens, "total": len(itens)}


@router.patch("/perfis/{perfil_ref}")
def patch_perfil(
    perfil_ref: str,
    body: PerfilPatchIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    with _db() as conn:
        try:
            return plataforma.atualizar_perfil(
                conn,
                perfil_ref=perfil_ref,
                actor_id=user[0],
                email=user[1],
                nome=body.nome,
                descricao=body.descricao,
                modelo_orquestrador=body.modelo_orquestrador,
                modelo_redator=body.modelo_redator,
                quota_perguntas_max=body.quota_perguntas_max,
                tools=body.tools,
                ativo=body.ativo,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/campanhas/{campanha_id}/tokens")
def tokens(
    campanha_id: str, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_gerir_campanha(conn, user[0], user[1], campanha_id)
        itens = plataforma.listar_tokens_campanha(conn, campanha_id)
        return {"itens": itens, "total": len(itens)}


@router.post("/campanhas/{campanha_id}/tokens")
def emitir_token(
    campanha_id: str,
    body: TokenIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_gerir_campanha(conn, user[0], user[1], campanha_id)
        try:
            return plataforma.emitir_token_campanha(
                conn,
                campanha_id=campanha_id,
                perfil=body.perfil,
                rotulo=body.rotulo,
                actor_id=user[0],
                nome=body.nome,
                email=body.email,
                quota_max=body.quota_max,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/eventos")
def eventos(
    campanha_id: str | None = None,
    usuario_id: str | None = None,
    limite: int = 100,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    with _db() as conn:
        plataforma.exigir_super(conn, user[1])
        itens = plataforma.listar_eventos(
            conn, campanha_id=campanha_id, usuario_id=usuario_id, limite=limite
        )
        return {"itens": itens, "total": len(itens)}


@router.get("/auditoria/resumo")
def auditoria_resumo(
    dias: int = 7,
    campanha_id: str | None = None,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    from gestao import auditoria

    with _db() as conn:
        plataforma.exigir_super(conn, user[1])
        return auditoria.resumo_uso(conn, dias=dias, campanha_id=campanha_id)


@router.get("/auditoria/interacoes")
def auditoria_interacoes(
    usuario_id: str | None = None,
    campanha_id: str | None = None,
    limite: int = 50,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    from gestao import auditoria

    with _db() as conn:
        plataforma.exigir_super(conn, user[1])
        itens = auditoria.listar_interacoes(
            conn, usuario_id=usuario_id, campanha_id=campanha_id, limite=limite
        )
        return {"itens": itens, "total": len(itens)}


@router.post("/auditoria/sugerir")
async def auditoria_sugerir(
    dias: int = 7,
    campanha_id: str | None = None,
    usar_llm: bool = True,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    from gestao import auditoria

    with _db() as conn:
        plataforma.exigir_super(conn, user[1])
        return await auditoria.sugerir_boas_praticas(
            conn,
            email_super=user[1],
            dias=dias,
            campanha_id=campanha_id,
            usar_llm=usar_llm,
        )
