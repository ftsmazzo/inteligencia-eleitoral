"""API HTTP Gestão sob /apura/api/gestao — JWT Apura + campanha_id."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apura.auth import decodificar_jwt, usuario_por_id
from gestao import dossie, equipe, memoria, motor, nominata_query, paineis, seed_radar, store
from gestao.schema import ensure_schema

router = APIRouter(prefix="/apura/api/gestao", tags=["gestao"])


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


def _campanha(user: tuple[str, str, str]) -> tuple[str, str]:
    with _db() as conn:
        row = store.campanha_do_usuario(conn, user[0])
    if not row:
        raise HTTPException(403, "Usuário sem campanha")
    return row


class IniciarIn(BaseModel):
    nome: str | None = Field(default=None, max_length=80)


class EscopoIn(BaseModel):
    ano_ref: int = 2026
    cd_cargo: int
    sg_uf: str | None = Field(default=None, max_length=2)
    sq_candidato: int
    nm_candidato: str = Field(min_length=1, max_length=200)
    nm_urna: str = Field(default="", max_length=120)
    sg_partido: str | None = Field(default=None, max_length=20)
    nr_candidato: int | None = None


class AmbienteIn(BaseModel):
    status: str = Field(description="rascunho|configurando|pronto")


class DossieIn(BaseModel):
    html: str = Field(min_length=40)
    nome_arquivo: str = Field(default="dossie.html", max_length=200)


class EquipeIn(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    nome: str = Field(default="", max_length=120)
    papel: str = Field(default="equipe", max_length=20)
    senha: str | None = Field(default=None, max_length=80)


def _exige_coordenador(conn, user: tuple[str, str, str]) -> None:
    papel = store.papel_usuario(conn, user[0])
    if papel != "coordenador":
        raise HTTPException(403, "Só o coordenador gera e gerencia usuários da equipe.")


@router.get("/status")
def status(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        st = store.get_status(conn, cid)
        try:
            conn.execute(
                "UPDATE ctl.apura_usuario SET papel = 'coordenador' WHERE id = %s::uuid AND COALESCE(papel,'equipe') <> 'coordenador'",
                (user[0],),
            )
        except Exception:
            pass
        st["papel"] = store.papel_usuario(conn, user[0])
        try:
            boot = equipe.garantir_bootstrap(conn, cid)
            st["bootstrap_equipe"] = {
                "email": boot.get("email") if boot else None,
                "criado": bool(boot and boot.get("criado")),
            }
        except Exception:
            st["bootstrap_equipe"] = {"ok": False}
        return st


@router.post("/iniciar")
def iniciar(body: IniciarIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        try:
            st = store.iniciar(conn, user[0], body.nome)
            st["papel"] = store.papel_usuario(conn, user[0])
            return st
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/candidatos")
def candidatos(
    ano: int = 2026,
    cargo: str = "governador",
    uf: str | None = None,
    q: str | None = None,
    limite: int = 200,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    _campanha(user)
    with _db() as conn:
        try:
            return nominata_query.listar_candidatos(
                conn, ano=ano, cargo=cargo, uf=uf or "", q=q, limite=limite
            )
        except Exception as exc:
            raise HTTPException(502, f"Falha na nominata ({exc})") from exc


@router.post("/escopo")
def escopo(body: EscopoIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    with _db() as conn:
        row = store.campanha_do_usuario(conn, user[0])
        if not row:
            raise HTTPException(403, "Usuário sem campanha")
        cid = row[0]
        st = store.get_status(conn, cid)
        if st.get("ambiente_status") == "legado":
            st = store.iniciar(conn, user[0], None)
            cid = st["campanha_id"]
        try:
            out = store.salvar_escopo(
                conn,
                cid,
                ano_ref=body.ano_ref,
                cd_cargo=body.cd_cargo,
                sg_uf=body.sg_uf or "",
                sq_candidato=body.sq_candidato,
                nm_candidato=body.nm_candidato,
                nm_urna=body.nm_urna or body.nm_candidato,
                sg_partido=body.sg_partido,
                nr_candidato=body.nr_candidato,
            )
            out["papel"] = store.papel_usuario(conn, user[0])
            return out
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/ambiente")
def ambiente(body: AmbienteIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return store.set_ambiente(conn, cid, body.status)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/motor")
def rodar_motor(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            result = motor.rodar_motor(conn, cid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Motor falhou ({type(exc).__name__}: {exc})") from exc
        try:
            seed = seed_radar.seed_radar_da_gestao(conn, cid)
            result["radar_seed"] = seed
        except Exception as exc:
            result["radar_seed"] = {"ok": False, "erro": str(exc)}
        return result


@router.get("/memoria")
def listar_memoria(
    tipo: str | None = None,
    limite: int = 50,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        itens = memoria.listar(conn, cid, tipo=tipo, limite=limite)
        return {"itens": itens, "total": len(itens)}


@router.post("/dossie")
def upload_dossie(body: DossieIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    if len(body.html) > 4_000_000:
        raise HTTPException(400, "HTML grande demais (máx. ~4 MB)")
    with _db() as conn:
        try:
            return dossie.ingerir_html(
                conn, cid, body.html, nome_arquivo=body.nome_arquivo or "dossie.html"
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/seed-radar")
def seed_radar_ep(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return seed_radar.seed_radar_da_gestao(conn, cid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/reset")
def reset_gestao(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    """Limpa memória, radar e escopo da campanha — recomeço."""
    cid, _ = _campanha(user)
    with _db() as conn:
        st = store.resetar_gestao(conn, cid)
        st["papel"] = store.papel_usuario(conn, user[0])
        st["reset"] = True
        return st


@router.post("/liberar")
def liberar(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        papel = store.papel_usuario(conn, user[0])
        if papel != "coordenador":
            # S4: qualquer user da campanha pode liberar se ainda não há coordenador formal
            try:
                conn.execute(
                    "UPDATE ctl.apura_usuario SET papel = 'coordenador' WHERE id = %s::uuid",
                    (user[0],),
                )
            except Exception:
                pass
        try:
            st = store.liberar_equipe(conn, cid)
            st["papel"] = "coordenador"
            return st
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/equipe")
def listar_equipe(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            equipe.garantir_bootstrap(conn, cid)
        except Exception:
            pass
        limpeza = {"n": 0, "apagados": []}
        try:
            limpeza = equipe.limpar_testes(conn, cid, manter_id=user[0])
        except Exception:
            pass
        itens = equipe.listar(conn, cid)
        papel = store.papel_usuario(conn, user[0])
        return {
            "itens": itens,
            "papel": papel,
            "pode_gerenciar": papel == "coordenador",
            "limpeza_testes": limpeza,
        }


@router.post("/equipe/limpar-testes")
def limpar_testes_ep(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        _exige_coordenador(conn, user)
        return equipe.limpar_testes(conn, cid, manter_id=user[0])


@router.delete("/equipe/{usuario_id}")
def apagar_equipe(usuario_id: str, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        _exige_coordenador(conn, user)
        try:
            return equipe.excluir(conn, cid, usuario_id, nao_excluir=user[0])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/equipe")
def criar_equipe(body: EquipeIn, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        _exige_coordenador(conn, user)
        try:
            return equipe.criar(
                conn, cid, email=body.email, nome=body.nome, papel=body.papel, senha=body.senha
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/equipe/{usuario_id}/senha")
def reset_senha_equipe(usuario_id: str, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        _exige_coordenador(conn, user)
        try:
            return equipe.redefinir_senha(conn, cid, usuario_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


class EquipeAtivoIn(BaseModel):
    ativo: bool = True


@router.post("/equipe/{usuario_id}/ativo")
def ativo_equipe(
    usuario_id: str, body: EquipeAtivoIn, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        _exige_coordenador(conn, user)
        try:
            return equipe.set_ativo(conn, cid, usuario_id, body.ativo)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/paineis")
def listar_paineis(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        return paineis.catalogo(store.get_status(conn, cid))


@router.get("/paineis/mapa-forca")
def painel_mapa(
    ano_eleitorado: int = 2022, user: tuple[str, str, str] = Depends(_usuario)
) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return paineis.mapa_forca(conn, cid, ano_eleitorado=ano_eleitorado)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/paineis/perfil-eleitorado")
def painel_perfil(ano: int = 2022, user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return paineis.perfil_eleitorado(conn, cid, ano=ano)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/paineis/socio-voto")
def painel_socio(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    cid, _ = _campanha(user)
    with _db() as conn:
        try:
            return paineis.socio_voto(conn, cid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
