"""Rotas FastAPI do painel Apura."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from apura.auth import (
    decodificar_jwt,
    login_usuario,
    registrar_usuario,
    usuario_por_id,
)
from apura.export import exportar_html, exportar_xlsx
from apura.orchestrator import executar_chat
from apura.skills import (
    MAX_ATIVAS,
    MAX_CONTEUDO,
    MAX_NOME,
    criar_skill,
    deletar_skill,
    listar_skills,
    texto_skills_ativas,
    atualizar_skill,
)

router = APIRouter(prefix="/apura/api", tags=["apura"])
_STATIC = Path(__file__).resolve().parents[1] / "static" / "apura"
_PATCH = Path(__file__).resolve().parents[1] / "sql" / "patch_apura.sql"
_PATCH_TOKENS = Path(__file__).resolve().parents[1] / "sql" / "patch_mcp_tokens.sql"
_SCHEMA_VER = 3
_READY_VER = 0


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _ensure_schema() -> None:
    global _READY_VER
    if _READY_VER >= _SCHEMA_VER:
        return
    if not _PATCH.exists():
        raise HTTPException(503, "Schema Apura indisponível")
    url = _ddl_url()
    if not url:
        raise HTTPException(503, "Banco indisponível")
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            if _PATCH_TOKENS.exists():
                conn.execute(_PATCH_TOKENS.read_text(encoding="utf-8"))
            conn.execute(_PATCH.read_text(encoding="utf-8"))
    except psycopg.Error as exc:
        raise HTTPException(503, f"Falha ao preparar banco Apura ({exc.pgcode or 'erro'})") from exc
    _READY_VER = _SCHEMA_VER


@contextmanager
def _db() -> Iterator[psycopg.Connection]:
    _ensure_schema()
    url = _ddl_url() or _db_url()
    if not url:
        raise HTTPException(503, "Banco indisponível")
    with psycopg.connect(url) as conn:
        yield conn


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticação necessária")
    return authorization[7:].strip()


def _usuario_atual(authorization: str | None = Header(default=None)) -> tuple[str, str, str]:
    payload = decodificar_jwt(_bearer(authorization))
    uid = payload["sub"]
    with _db() as conn:
        return usuario_por_id(conn, uid)


class RegistroIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    nome: str = Field(min_length=2, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str


class SessaoIn(BaseModel):
    titulo: str = Field(default="Nova conversa", max_length=120)


class ChatIn(BaseModel):
    sessao_id: str
    mensagem: str = Field(min_length=1, max_length=8000)


class ExportIn(BaseModel):
    mensagem_id: str


class SkillIn(BaseModel):
    nome: str = Field(min_length=2, max_length=MAX_NOME)
    conteudo: str = Field(min_length=10, max_length=MAX_CONTEUDO)
    ativo: bool = False


class SkillPatchIn(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=MAX_NOME)
    conteudo: str | None = Field(default=None, min_length=10, max_length=MAX_CONTEUDO)
    ativo: bool | None = None


@router.post("/auth/registrar")
def registrar(body: RegistroIn) -> dict[str, str]:
    try:
        with _db() as conn:
            return registrar_usuario(conn, body.email, body.senha, body.nome)
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "E-mail já cadastrado") from exc
    except psycopg.errors.InsufficientPrivilege as exc:
        raise HTTPException(503, "Permissão insuficiente no banco — contacte o administrador") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, f"Banco indisponível para cadastro ({exc.pgcode or 'erro'})") from exc
    except Exception as exc:
        raise HTTPException(500, f"Erro ao criar conta: {type(exc).__name__}") from exc


@router.post("/auth/login")
def login(body: LoginIn) -> dict[str, str]:
    with _db() as conn:
        return login_usuario(conn, body.email, body.senha)


@router.get("/auth/eu")
def eu(user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    return {"id": user[0], "email": user[1]}


@router.get("/sessoes")
def listar_sessoes(user: tuple[str, str, str] = Depends(_usuario_atual)) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id::text, titulo, criado_em, atualizado_em
            FROM ctl.apura_sessao
            WHERE usuario_id = %s::uuid
            ORDER BY atualizado_em DESC
            LIMIT 50
            """,
            (user[0],),
        ).fetchall()
    return [
        {"id": r[0], "titulo": r[1], "criado_em": r[2].isoformat(), "atualizado_em": r[3].isoformat()}
        for r in rows
    ]


@router.post("/sessoes")
def criar_sessao(body: SessaoIn, user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    sid = str(uuid.uuid4())
    titulo = body.titulo.strip()
    try:
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO ctl.apura_sessao (id, usuario_id, titulo)
                VALUES (%s::uuid, %s::uuid, %s)
                """,
                (sid, user[0], titulo),
            )
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(400, "Usuário não encontrado para criar conversa") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, f"Não foi possível criar conversa ({exc.pgcode or 'erro'})") from exc
    except Exception as exc:
        raise HTTPException(500, f"Erro ao criar conversa: {type(exc).__name__}: {exc}") from exc
    return {"id": sid, "titulo": titulo}


@router.get("/sessoes/{sessao_id}/mensagens")
def listar_mensagens(sessao_id: str, user: tuple[str, str, str] = Depends(_usuario_atual)) -> list[dict[str, Any]]:
    with _db() as conn:
        ok = conn.execute(
            "SELECT 1 FROM ctl.apura_sessao WHERE id = %s AND usuario_id = %s",
            (sessao_id, user[0]),
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Conversa não encontrada")
        rows = conn.execute(
            """
            SELECT id::text, papel, conteudo, dados_json, criado_em
            FROM ctl.apura_mensagem
            WHERE sessao_id = %s
            ORDER BY criado_em
            """,
            (sessao_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "papel": r[1],
            "conteudo": r[2],
            "dados": r[3],
            "criado_em": r[4].isoformat(),
        }
        for r in rows
    ]


@router.post("/chat")
async def chat(
    body: ChatIn,
    user: tuple[str, str, str] = Depends(_usuario_atual),
) -> StreamingResponse:
    uid, _, mcp_token = user
    try:
        with _db() as conn:
            ok = conn.execute(
                "SELECT titulo FROM ctl.apura_sessao WHERE id = %s::uuid AND usuario_id = %s::uuid",
                (body.sessao_id, uid),
            ).fetchone()
            if not ok:
                raise HTTPException(404, "Conversa não encontrada")
            conn.execute(
                """
                INSERT INTO ctl.apura_mensagem (sessao_id, papel, conteudo)
                VALUES (%s::uuid, 'user', %s)
                """,
                (body.sessao_id, body.mensagem.strip()),
            )
            if ok[0] == "Nova conversa":
                titulo = body.mensagem.strip()[:60] + ("…" if len(body.mensagem.strip()) > 60 else "")
                conn.execute(
                    "UPDATE ctl.apura_sessao SET titulo = %s, atualizado_em = now() WHERE id = %s::uuid",
                    (titulo, body.sessao_id),
                )
            else:
                conn.execute(
                    "UPDATE ctl.apura_sessao SET atualizado_em = now() WHERE id = %s::uuid",
                    (body.sessao_id,),
                )
            hist_rows = conn.execute(
                """
                SELECT papel, conteudo FROM ctl.apura_mensagem
                WHERE sessao_id = %s::uuid AND papel IN ('user', 'assistant')
                ORDER BY criado_em
                """,
                (body.sessao_id,),
            ).fetchall()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, f"Falha ao preparar mensagem ({exc.pgcode or 'erro'})") from exc

    historico = [{"papel": r[0], "conteudo": r[1]} for r in hist_rows]

    with _db() as conn:
        skills_txt = texto_skills_ativas(conn, uid)

    async def stream_and_save() -> Any:
        final_content = ""
        final_dados = None
        async for chunk in executar_chat(historico, mcp_token, skills_txt):
            yield chunk
            if chunk.startswith("event: done"):
                line = chunk.split("\n", 1)[1]
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    final_content = payload.get("conteudo", "")
                    final_dados = payload.get("dados")
                    if payload.get("relatorio_html"):
                        base = dict(final_dados) if isinstance(final_dados, dict) else {}
                        base["relatorio_html"] = payload["relatorio_html"]
                        final_dados = base
        if final_content:
            with _db() as conn:
                conn.execute(
                    """
                    INSERT INTO ctl.apura_mensagem (sessao_id, papel, conteudo, dados_json)
                    VALUES (%s::uuid, 'assistant', %s, %s)
                    """,
                    (body.sessao_id, final_content, json.dumps(final_dados) if final_dados else None),
                )

    return StreamingResponse(
        stream_and_save(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/export/xlsx")
def export_xlsx(body: ExportIn, user: tuple[str, str, str] = Depends(_usuario_atual)) -> Response:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT m.conteudo, m.dados_json, s.titulo
            FROM ctl.apura_mensagem m
            JOIN ctl.apura_sessao s ON s.id = m.sessao_id
            WHERE m.id = %s AND s.usuario_id = %s AND m.papel = 'assistant'
            """,
            (body.mensagem_id, user[0]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Mensagem não encontrada")
    dados = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    blob = exportar_xlsx(dados, row[2] or "Apura")
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="apura-dados.xlsx"'},
    )


@router.post("/export/html")
def export_html_route(body: ExportIn, user: tuple[str, str, str] = Depends(_usuario_atual)) -> Response:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT m.conteudo, m.dados_json, s.titulo
            FROM ctl.apura_mensagem m
            JOIN ctl.apura_sessao s ON s.id = m.sessao_id
            WHERE m.id = %s AND s.usuario_id = %s AND m.papel = 'assistant'
            """,
            (body.mensagem_id, user[0]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Mensagem não encontrada")
    dados = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    html = exportar_html(dados, row[0] or "", row[2] or "Apura")
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="apura-relatorio.html"'},
    )


@router.get("/skills")
def api_listar_skills(user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, Any]:
    with _db() as conn:
        items = listar_skills(conn, user[0])
    return {"items": items, "max_ativas": MAX_ATIVAS}


@router.post("/skills")
def api_criar_skill(body: SkillIn, user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    with _db() as conn:
        return criar_skill(conn, user[0], body.nome, body.conteudo, body.ativo)


@router.patch("/skills/{skill_id}")
def api_atualizar_skill(
    skill_id: str,
    body: SkillPatchIn,
    user: tuple[str, str, str] = Depends(_usuario_atual),
) -> dict[str, str]:
    with _db() as conn:
        atualizar_skill(conn, user[0], skill_id, body.nome, body.conteudo, body.ativo)
    return {"status": "ok"}


@router.delete("/skills/{skill_id}")
def api_deletar_skill(skill_id: str, user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    with _db() as conn:
        deletar_skill(conn, user[0], skill_id)
    return {"status": "ok"}


def pagina_apura() -> HTMLResponse:
    path = _STATIC / "index.html"
    if not path.exists():
        raise HTTPException(404, "Apura indisponível")
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})
