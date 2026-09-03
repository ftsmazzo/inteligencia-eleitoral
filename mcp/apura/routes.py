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
    consumir_pergunta_demo,
    decodificar_jwt,
    login_usuario,
    quota_usuario,
    registrar_usuario,
    usuario_por_id,
)
from apura.cadastro import entregar_token, listar_campanhas_ativas, solicitar_cadastro
from apura.export import exportar_html, exportar_xlsx
from apura.orchestrator import executar_chat
from apura.prompt import SKILL_NARRATIVA_DEFAULT, SKILL_WAR_ROOM_DEFAULT
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
_SQL = Path(__file__).resolve().parents[1] / "sql"
if not (_SQL / "patch_apura.sql").exists():
    _SQL = Path(__file__).resolve().parents[2] / "sql"
_PATCH = _SQL / "patch_apura.sql"
_PATCH_TOKENS = _SQL / "patch_mcp_tokens.sql"
_PATCH_GESTAO = _SQL / "patch_gestao.sql"
_SCHEMA_VER = 8
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
            if _PATCH_GESTAO.exists():
                conn.execute(_PATCH_GESTAO.read_text(encoding="utf-8"))
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
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _registrar_ultima_sessao(conn: psycopg.Connection, usuario_id: str, sessao_id: str) -> None:
    conn.execute(
        """
        UPDATE ctl.apura_usuario SET ultima_sessao_id = %s::uuid
        WHERE id = %s::uuid
        """,
        (sessao_id, usuario_id),
    )


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


class SessaoPatchIn(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=120)
    fixada: bool | None = None


class ChatIn(BaseModel):
    sessao_id: str
    mensagem: str = Field(min_length=1, max_length=8000)
    modo_narrativa: bool = False


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


class CadastroSolicitarIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    email: EmailStr
    telefone: str = Field(default="", max_length=32)
    campanha_nome: str = Field(min_length=2, max_length=80)


@router.get("/cadastro/campanhas")
def cadastro_campanhas() -> list[dict[str, str]]:
    with _db() as conn:
        return listar_campanhas_ativas(conn)


@router.post("/cadastro/solicitar")
def cadastro_solicitar(body: CadastroSolicitarIn) -> dict[str, str]:
    with _db() as conn:
        return solicitar_cadastro(
            conn,
            body.nome,
            str(body.email),
            body.telefone,
            body.campanha_nome,
        )


@router.get("/cadastro/token/{request_id}")
def cadastro_token(request_id: str) -> dict[str, str]:
    with _db() as conn:
        token = entregar_token(conn, request_id)
    return {"token": token}


@router.post("/auth/registrar")
def registrar(body: RegistroIn) -> dict[str, str]:
    raise HTTPException(
        403,
        "Cadastro público desativado. Peça acesso pelo formulário ou WhatsApp na página inicial.",
    )


@router.post("/auth/login")
def login(body: LoginIn) -> dict[str, str]:
    with _db() as conn:
        return login_usuario(conn, body.email, body.senha)


@router.get("/auth/eu")
def eu(user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT u.ultima_sessao_id::text, u.campanha_id::text, c.nome
            FROM ctl.apura_usuario u
            LEFT JOIN ctl.campanha c ON c.id = u.campanha_id
            WHERE u.id = %s::uuid
            """,
            (user[0],),
        ).fetchone()
        q = quota_usuario(conn, user[0])
    return {
        "id": user[0],
        "email": user[1],
        "ultima_sessao_id": row[0] if row else None,
        "campanha_id": row[1] if row else None,
        "campanha_nome": row[2] if row else None,
        "quota": q,
    }


@router.get("/sessoes")
def listar_sessoes(user: tuple[str, str, str] = Depends(_usuario_atual)) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT s.id::text, s.titulo, s.fixada, s.criado_em, s.atualizado_em,
                   (SELECT COUNT(*)::int FROM ctl.apura_mensagem m WHERE m.sessao_id = s.id)
            FROM ctl.apura_sessao s
            WHERE s.usuario_id = %s::uuid
            ORDER BY s.fixada DESC, s.atualizado_em DESC
            LIMIT 50
            """,
            (user[0],),
        ).fetchall()
    return [
        {
            "id": r[0],
            "titulo": r[1],
            "fixada": bool(r[2]),
            "criado_em": r[3].isoformat(),
            "atualizado_em": r[4].isoformat(),
            "num_mensagens": int(r[5]),
        }
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
            _registrar_ultima_sessao(conn, user[0], sid)
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(400, "Usuário não encontrado para criar conversa") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, f"Não foi possível criar conversa ({exc.pgcode or 'erro'})") from exc
    except Exception as exc:
        raise HTTPException(500, f"Erro ao criar conversa: {type(exc).__name__}: {exc}") from exc
    return {"id": sid, "titulo": titulo}


@router.patch("/sessoes/{sessao_id}")
def atualizar_sessao(
    sessao_id: str,
    body: SessaoPatchIn,
    user: tuple[str, str, str] = Depends(_usuario_atual),
) -> dict[str, Any]:
    if body.titulo is None and body.fixada is None:
        raise HTTPException(400, "Nada para atualizar")
    with _db() as conn:
        ok = conn.execute(
            "SELECT 1 FROM ctl.apura_sessao WHERE id = %s::uuid AND usuario_id = %s::uuid",
            (sessao_id, user[0]),
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Conversa não encontrada")
        if body.fixada is True:
            conn.execute(
                "UPDATE ctl.apura_sessao SET fixada = false WHERE usuario_id = %s::uuid",
                (user[0],),
            )
        sets: list[str] = ["atualizado_em = now()"]
        params: list[Any] = []
        if body.titulo is not None:
            sets.append("titulo = %s")
            params.append(body.titulo.strip())
        if body.fixada is not None:
            sets.append("fixada = %s")
            params.append(body.fixada)
        params.extend([sessao_id, user[0]])
        conn.execute(
            f"UPDATE ctl.apura_sessao SET {', '.join(sets)} WHERE id = %s::uuid AND usuario_id = %s::uuid",
            params,
        )
        row = conn.execute(
            "SELECT id::text, titulo, fixada FROM ctl.apura_sessao WHERE id = %s::uuid",
            (sessao_id,),
        ).fetchone()
    return {"id": row[0], "titulo": row[1], "fixada": bool(row[2])}


@router.delete("/sessoes")
def apagar_todas_sessoes(user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    with _db() as conn:
        conn.execute("DELETE FROM ctl.apura_sessao WHERE usuario_id = %s::uuid", (user[0],))
    return {"status": "ok"}


@router.delete("/sessoes/{sessao_id}")
def apagar_sessao(sessao_id: str, user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, str]:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM ctl.apura_sessao WHERE id = %s::uuid AND usuario_id = %s::uuid RETURNING id",
            (sessao_id, user[0]),
        ).fetchone()
        if not cur:
            raise HTTPException(404, "Conversa não encontrada")
    return {"status": "ok"}


@router.get("/sessoes/{sessao_id}/mensagens")
def listar_mensagens(sessao_id: str, user: tuple[str, str, str] = Depends(_usuario_atual)) -> list[dict[str, Any]]:
    with _db() as conn:
        ok = conn.execute(
            "SELECT 1 FROM ctl.apura_sessao WHERE id = %s AND usuario_id = %s",
            (sessao_id, user[0]),
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Conversa não encontrada")
        _registrar_ultima_sessao(conn, user[0], sessao_id)
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
            quota_info = consumir_pergunta_demo(conn, uid)
            _registrar_ultima_sessao(conn, uid, body.sessao_id)
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
        if SKILL_WAR_ROOM_DEFAULT not in skills_txt:
            skills_txt = (SKILL_WAR_ROOM_DEFAULT + "\n\n" + skills_txt).strip()
        if body.modo_narrativa and SKILL_NARRATIVA_DEFAULT not in skills_txt:
            skills_txt = (skills_txt + "\n\n" + SKILL_NARRATIVA_DEFAULT).strip()

    async def stream_and_save() -> Any:
        final_content = ""
        final_dados = None
        async for chunk in executar_chat(historico, mcp_token, skills_txt, body.modo_narrativa):
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Demo-Quota-Restantes": (
                str(quota_info["restantes"]) if quota_info.get("restantes") is not None else "ilimitado"
            ),
        },
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
def api_criar_skill(body: SkillIn, user: tuple[str, str, str] = Depends(_usuario_atual)) -> dict[str, Any]:
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
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


def pagina_cadastro() -> HTMLResponse:
    path = _STATIC / "cadastro.html"
    if not path.exists():
        raise HTTPException(404, "Cadastro indisponível")
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )
