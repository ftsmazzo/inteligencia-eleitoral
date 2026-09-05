"""Plataforma multi-campanha: frota, Perfis, membros, tokens MCP, auditoria.

Contrato: docs/CONTRATO-PLATAFORMA-GESTAO.md
"""
from __future__ import annotations

import json
import re
import secrets
import uuid
from typing import Any

import psycopg

from gestao.store import CARGOS, UFS, get_status

MODULOS_DEFAULT = ("chat", "radar", "clima", "dados_mcp", "gestao_campanha")


def _slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (nome or "").lower()).strip("-")
    return (s or "campanha")[:80]


def registrar_evento(
    conn: psycopg.Connection,
    *,
    acao: str,
    usuario_id: str | None = None,
    campanha_id: str | None = None,
    token_rotulo: str | None = None,
    detalhe: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ctl.evento_acesso
          (usuario_id, campanha_id, token_rotulo, acao, detalhe_json, ip, user_agent)
        VALUES (
          %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s, %s
        )
        """,
        (
            usuario_id,
            campanha_id,
            token_rotulo,
            acao,
            json.dumps(detalhe or {}, ensure_ascii=False),
            ip,
            user_agent,
        ),
    )


def eh_super_gestor(conn: psycopg.Connection, email: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM ctl.plataforma_super_gestor
        WHERE lower(email) = lower(%s) AND ativo IS TRUE
        """,
        (email,),
    ).fetchone()
    return bool(row)


def exigir_super(conn: psycopg.Connection, email: str) -> None:
    if not eh_super_gestor(conn, email):
        from fastapi import HTTPException

        raise HTTPException(403, "Apenas super gestores")


def membro_ativo(
    conn: psycopg.Connection, usuario_id: str, campanha_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT m.id::text, m.papel_campanha, m.perfil_id::text,
               p.slug, p.nome
        FROM ctl.campanha_membro m
        JOIN ctl.perfil p ON p.id = m.perfil_id
        WHERE m.usuario_id = %s::uuid
          AND m.campanha_id = %s::uuid
          AND m.ativo IS TRUE
        """,
        (usuario_id, campanha_id),
    ).fetchone()
    if not row:
        return None
    return {
        "membro_id": row[0],
        "papel_campanha": row[1],
        "perfil_id": row[2],
        "perfil_slug": row[3],
        "perfil_nome": row[4],
    }


def pode_gerir_campanha(
    conn: psycopg.Connection, usuario_id: str, email: str, campanha_id: str
) -> bool:
    if eh_super_gestor(conn, email):
        return True
    m = membro_ativo(conn, usuario_id, campanha_id)
    return bool(m and m["papel_campanha"] == "coordenador")


def exigir_gerir_campanha(
    conn: psycopg.Connection, usuario_id: str, email: str, campanha_id: str
) -> None:
    if not pode_gerir_campanha(conn, usuario_id, email, campanha_id):
        from fastapi import HTTPException

        raise HTTPException(403, "Sem permissão para gerir esta campanha")


def campanha_ativa_do_usuario(
    conn: psycopg.Connection, usuario_id: str
) -> tuple[str, str] | None:
    """Resolve campanha de trabalho: campanha_ativa_id, senão legado campanha_id."""
    row = conn.execute(
        """
        SELECT COALESCE(u.campanha_ativa_id, u.campanha_id)::text, c.nome
        FROM ctl.apura_usuario u
        LEFT JOIN ctl.campanha c ON c.id = COALESCE(u.campanha_ativa_id, u.campanha_id)
        WHERE u.id = %s::uuid AND u.ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0] or not row[1]:
        return None
    return row[0], row[1]


def contexto_usuario(conn: psycopg.Connection, usuario_id: str, email: str) -> dict[str, Any]:
    super_g = eh_super_gestor(conn, email)
    ativa = campanha_ativa_do_usuario(conn, usuario_id)
    vinculos = listar_vinculos(conn, usuario_id)
    return {
        "usuario_id": usuario_id,
        "email": email,
        "is_super_gestor": super_g,
        "campanha_ativa_id": ativa[0] if ativa else None,
        "campanha_ativa_nome": ativa[1] if ativa else None,
        "vinculos": vinculos,
        "precisa_seletor": len(vinculos) > 1 and not super_g,
        "cargos": list(CARGOS),
        "ufs": list(UFS),
    }


def listar_vinculos(conn: psycopg.Connection, usuario_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id::text, c.nome, c.ambiente_status, c.sg_uf, c.nm_urna,
               m.papel_campanha, p.slug, p.nome,
               COALESCE(c.equipe_liberada, false)
        FROM ctl.campanha_membro m
        JOIN ctl.campanha c ON c.id = m.campanha_id
        JOIN ctl.perfil p ON p.id = m.perfil_id
        WHERE m.usuario_id = %s::uuid AND m.ativo IS TRUE AND c.ativo IS TRUE
        ORDER BY c.nome
        """,
        (usuario_id,),
    ).fetchall()
    return [
        {
            "campanha_id": r[0],
            "campanha_nome": r[1],
            "ambiente_status": r[2],
            "sg_uf": r[3],
            "nm_urna": r[4],
            "papel_campanha": r[5],
            "perfil_slug": r[6],
            "perfil_nome": r[7],
            "equipe_liberada": bool(r[8]),
        }
        for r in rows
    ]


def listar_campanhas(
    conn: psycopg.Connection, usuario_id: str, email: str
) -> list[dict[str, Any]]:
    if eh_super_gestor(conn, email):
        rows = conn.execute(
            """
            SELECT c.id::text, c.nome, c.ambiente_status, c.sg_uf, c.cd_cargo,
                   c.nm_urna, c.nm_candidato, COALESCE(c.equipe_liberada, false),
                   c.atualizado_em,
                   (SELECT COUNT(*)::int FROM ctl.campanha_membro m
                    WHERE m.campanha_id = c.id AND m.ativo IS TRUE),
                   (SELECT COALESCE(json_agg(cm.codigo ORDER BY cm.codigo), '[]'::json)
                    FROM ctl.campanha_modulo cm
                    WHERE cm.campanha_id = c.id AND cm.ativo IS TRUE)
            FROM ctl.campanha c
            WHERE c.ativo IS TRUE
            ORDER BY c.nome
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT c.id::text, c.nome, c.ambiente_status, c.sg_uf, c.cd_cargo,
                   c.nm_urna, c.nm_candidato, COALESCE(c.equipe_liberada, false),
                   c.atualizado_em,
                   (SELECT COUNT(*)::int FROM ctl.campanha_membro m2
                    WHERE m2.campanha_id = c.id AND m2.ativo IS TRUE),
                   (SELECT COALESCE(json_agg(cm.codigo ORDER BY cm.codigo), '[]'::json)
                    FROM ctl.campanha_modulo cm
                    WHERE cm.campanha_id = c.id AND cm.ativo IS TRUE)
            FROM ctl.campanha_membro m
            JOIN ctl.campanha c ON c.id = m.campanha_id
            WHERE m.usuario_id = %s::uuid AND m.ativo IS TRUE AND c.ativo IS TRUE
            ORDER BY c.nome
            """,
            (usuario_id,),
        ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        mods = r[10]
        if isinstance(mods, str):
            mods = json.loads(mods)
        cargo_label = next((c["label"] for c in CARGOS if c["cd_cargo"] == r[4]), None)
        out.append(
            {
                "campanha_id": r[0],
                "nome": r[1],
                "ambiente_status": r[2],
                "sg_uf": r[3],
                "cd_cargo": r[4],
                "cargo_label": cargo_label,
                "nm_urna": r[5],
                "nm_candidato": r[6],
                "equipe_liberada": bool(r[7]),
                "atualizado_em": r[8].isoformat() if r[8] else None,
                "membros_count": int(r[9] or 0),
                "modulos": mods or [],
            }
        )
    return out


def detalhe_campanha(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    if not st:
        from fastapi import HTTPException

        raise HTTPException(404, "Campanha não encontrada")
    mods = conn.execute(
        """
        SELECT codigo, ativo, meta_json
        FROM ctl.campanha_modulo
        WHERE campanha_id = %s::uuid
        ORDER BY codigo
        """,
        (campanha_id,),
    ).fetchall()
    st["modulos"] = [
        {
            "codigo": m[0],
            "ativo": bool(m[1]),
            "meta_json": m[2] if isinstance(m[2], dict) else (json.loads(m[2]) if m[2] else {}),
        }
        for m in mods
    ]
    return st


def _nome_unico(conn: psycopg.Connection, nome: str) -> str:
    slug = _slug(nome)
    base = slug
    n = 1
    while conn.execute("SELECT 1 FROM ctl.campanha WHERE nome = %s", (slug,)).fetchone():
        n += 1
        slug = f"{base}-{n}"
    return slug


def provisionar_modulos(conn: psycopg.Connection, campanha_id: str) -> None:
    for codigo in MODULOS_DEFAULT:
        conn.execute(
            """
            INSERT INTO ctl.campanha_modulo (campanha_id, codigo, ativo)
            VALUES (%s::uuid, %s, TRUE)
            ON CONFLICT (campanha_id, codigo) DO NOTHING
            """,
            (campanha_id, codigo),
        )


def criar_campanha(
    conn: psycopg.Connection,
    *,
    usuario_id: str,
    email: str,
    nome: str,
    rotulo: str | None = None,
) -> dict[str, Any]:
    exigir_super(conn, email)
    display = (rotulo or nome or "").strip()
    if len(display) < 2:
        raise ValueError("Nome da campanha obrigatório")
    slug = _nome_unico(conn, nome if nome.strip() else display)
    cid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO ctl.campanha (id, nome, ativo, ambiente_status, atualizado_em)
        VALUES (%s::uuid, %s, TRUE, 'rascunho', now())
        """,
        (cid, slug),
    )
    # Guarda rótulo humano em escopo_json sem marcar escopo eleitoral
    conn.execute(
        """
        UPDATE ctl.campanha
        SET escopo_json = COALESCE(escopo_json, '{}'::jsonb) || %s::jsonb
        WHERE id = %s::uuid
        """,
        (json.dumps({"rotulo": display}, ensure_ascii=False), cid),
    )
    provisionar_modulos(conn, cid)
    registrar_evento(
        conn,
        acao="criar_campanha",
        usuario_id=usuario_id,
        campanha_id=cid,
        detalhe={"nome": slug, "rotulo": display},
    )
    return detalhe_campanha(conn, cid)


def entrar_campanha(
    conn: psycopg.Connection,
    *,
    usuario_id: str,
    email: str,
    campanha_id: str,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id::text, nome FROM ctl.campanha WHERE id = %s::uuid AND ativo IS TRUE",
        (campanha_id,),
    ).fetchone()
    if not row:
        from fastapi import HTTPException

        raise HTTPException(404, "Campanha não encontrada")

    if not eh_super_gestor(conn, email):
        if not membro_ativo(conn, usuario_id, campanha_id):
            from fastapi import HTTPException

            raise HTTPException(403, "Você não é membro desta campanha")

    conn.execute(
        """
        UPDATE ctl.apura_usuario
        SET campanha_ativa_id = %s::uuid,
            campanha_id = %s::uuid
        WHERE id = %s::uuid
        """,
        (campanha_id, campanha_id, usuario_id),
    )
    registrar_evento(
        conn,
        acao="entrar_campanha",
        usuario_id=usuario_id,
        campanha_id=campanha_id,
    )
    ctx = contexto_usuario(conn, usuario_id, email)
    ctx["status"] = detalhe_campanha(conn, campanha_id)
    return ctx


def sair_campanha_ativa(
    conn: psycopg.Connection, *, usuario_id: str, email: str
) -> dict[str, Any]:
    """Limpa campanha ativa (super volta à frota). Membros comuns mantêm legado campanha_id."""
    conn.execute(
        "UPDATE ctl.apura_usuario SET campanha_ativa_id = NULL WHERE id = %s::uuid",
        (usuario_id,),
    )
    registrar_evento(conn, acao="sair_campanha", usuario_id=usuario_id)
    return contexto_usuario(conn, usuario_id, email)


def listar_membros(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT m.id::text, u.id::text, u.email, u.nome, m.papel_campanha,
               p.id::text, p.slug, p.nome, m.ativo, m.criado_em
        FROM ctl.campanha_membro m
        JOIN ctl.apura_usuario u ON u.id = m.usuario_id
        JOIN ctl.perfil p ON p.id = m.perfil_id
        WHERE m.campanha_id = %s::uuid
        ORDER BY m.papel_campanha DESC, u.nome, u.email
        """,
        (campanha_id,),
    ).fetchall()
    return [
        {
            "membro_id": r[0],
            "usuario_id": r[1],
            "email": r[2],
            "nome": r[3],
            "papel_campanha": r[4],
            "perfil_id": r[5],
            "perfil_slug": r[6],
            "perfil_nome": r[7],
            "ativo": bool(r[8]),
            "criado_em": r[9].isoformat() if r[9] else None,
        }
        for r in rows
    ]


def _perfil_por_slug_ou_id(
    conn: psycopg.Connection, perfil: str, *, so_ativos: bool = True
) -> tuple[str, str]:
    if so_ativos:
        row = conn.execute(
            """
            SELECT id::text, slug FROM ctl.perfil
            WHERE (id::text = %s OR slug = %s) AND ativo IS TRUE
            """,
            (perfil, perfil),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id::text, slug FROM ctl.perfil
            WHERE id::text = %s OR slug = %s
            """,
            (perfil, perfil),
        ).fetchone()
    if not row:
        raise ValueError("Perfil inválido" + (" ou inativo" if so_ativos else ""))
    return row[0], row[1]


def upsert_membro(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    email: str,
    perfil: str,
    papel_campanha: str = "equipe",
    nome: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    papel = (papel_campanha or "equipe").strip().lower()
    if papel not in ("coordenador", "equipe"):
        raise ValueError("papel_campanha deve ser coordenador|equipe")
    perfil_id, perfil_slug = _perfil_por_slug_ou_id(conn, perfil)
    em = email.strip().lower()
    user = conn.execute(
        """
        SELECT id::text, nome FROM ctl.apura_usuario
        WHERE lower(email) = %s AND ativo IS TRUE
        """,
        (em,),
    ).fetchone()
    if not user:
        raise ValueError(
            "Usuário ainda não tem conta Apura. Peça que se registre ou cadastre a pessoa antes."
        )
    uid, unome = user[0], user[1]
    if nome and nome.strip() and not (unome or "").strip():
        conn.execute(
            "UPDATE ctl.apura_usuario SET nome = %s WHERE id = %s::uuid",
            (nome.strip()[:120], uid),
        )
    conn.execute(
        """
        INSERT INTO ctl.campanha_membro
          (campanha_id, usuario_id, perfil_id, papel_campanha, ativo, atualizado_em)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s, TRUE, now())
        ON CONFLICT (campanha_id, usuario_id) DO UPDATE SET
          perfil_id = EXCLUDED.perfil_id,
          papel_campanha = EXCLUDED.papel_campanha,
          ativo = TRUE,
          atualizado_em = now()
        """,
        (campanha_id, uid, perfil_id, papel),
    )
    # Legado: se usuário não tem campanha_id, aponta para esta
    conn.execute(
        """
        UPDATE ctl.apura_usuario
        SET campanha_id = COALESCE(campanha_id, %s::uuid),
            papel = CASE
              WHEN %s = 'coordenador' THEN 'coordenador'
              ELSE COALESCE(papel, 'equipe')
            END
        WHERE id = %s::uuid
        """,
        (campanha_id, papel, uid),
    )
    registrar_evento(
        conn,
        acao="membro_upsert",
        usuario_id=actor_id,
        campanha_id=campanha_id,
        detalhe={"email": em, "perfil": perfil_slug, "papel": papel},
    )
    membros = listar_membros(conn, campanha_id)
    return next(m for m in membros if m["usuario_id"] == uid)


def desativar_membro(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    membro_id: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE ctl.campanha_membro
        SET ativo = FALSE, atualizado_em = now()
        WHERE id = %s::uuid AND campanha_id = %s::uuid
        RETURNING usuario_id::text
        """,
        (membro_id, campanha_id),
    ).fetchone()
    if not row:
        from fastapi import HTTPException

        raise HTTPException(404, "Membro não encontrado")
    registrar_evento(
        conn,
        acao="membro_desativar",
        usuario_id=actor_id,
        campanha_id=campanha_id,
        detalhe={"membro_id": membro_id, "usuario_id": row[0]},
    )
    return {"ok": True, "membro_id": membro_id}


def listar_perfis(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id::text, p.slug, p.nome, p.descricao,
               p.modelo_orquestrador, p.modelo_redator,
               p.quota_perguntas_max, p.ativo, p.sistema,
               COALESCE(
                 (SELECT json_agg(t.tool_name ORDER BY t.tool_name)
                  FROM ctl.perfil_tool t WHERE t.perfil_id = p.id),
                 '[]'::json
               )
        FROM ctl.perfil p
        ORDER BY p.sistema DESC, p.nome
        """
    ).fetchall()
    out = []
    for r in rows:
        tools = r[9]
        if isinstance(tools, str):
            tools = json.loads(tools)
        out.append(
            {
                "perfil_id": r[0],
                "slug": r[1],
                "nome": r[2],
                "descricao": r[3],
                "modelo_orquestrador": r[4],
                "modelo_redator": r[5],
                "quota_perguntas_max": r[6],
                "ativo": bool(r[7]),
                "sistema": bool(r[8]),
                "tools": tools or [],
            }
        )
    return out


def atualizar_perfil(
    conn: psycopg.Connection,
    *,
    perfil_ref: str,
    actor_id: str,
    email: str,
    nome: str | None = None,
    descricao: str | None = None,
    modelo_orquestrador: str | None = None,
    modelo_redator: str | None = None,
    quota_perguntas_max: int | None = None,
    tools: list[str] | None = None,
    ativo: bool | None = None,
) -> dict[str, Any]:
    exigir_super(conn, email)
    perfil_id, slug = _perfil_por_slug_ou_id(conn, perfil_ref, so_ativos=False)
    sets: list[str] = ["atualizado_em = now()"]
    params: list[Any] = []
    if nome is not None:
        sets.append("nome = %s")
        params.append(nome.strip()[:80])
    if descricao is not None:
        sets.append("descricao = %s")
        params.append(descricao.strip()[:500])
    if modelo_orquestrador is not None:
        sets.append("modelo_orquestrador = %s")
        params.append(modelo_orquestrador.strip()[:120])
    if modelo_redator is not None:
        sets.append("modelo_redator = %s")
        params.append(modelo_redator.strip()[:120])
    if quota_perguntas_max is not None:
        sets.append("quota_perguntas_max = %s")
        params.append(quota_perguntas_max if quota_perguntas_max > 0 else None)
    if ativo is not None:
        sets.append("ativo = %s")
        params.append(ativo)
    params.append(perfil_id)
    conn.execute(
        f"UPDATE ctl.perfil SET {', '.join(sets)} WHERE id = %s::uuid",
        params,
    )
    if tools is not None:
        clean = sorted({t.strip() for t in tools if t and t.strip()})
        conn.execute("DELETE FROM ctl.perfil_tool WHERE perfil_id = %s::uuid", (perfil_id,))
        for t in clean:
            conn.execute(
                "INSERT INTO ctl.perfil_tool (perfil_id, tool_name) VALUES (%s::uuid, %s)",
                (perfil_id, t),
            )
    registrar_evento(
        conn,
        acao="perfil_update",
        usuario_id=actor_id,
        detalhe={"perfil": slug, "tools_count": len(tools) if tools is not None else None},
    )
    return next(p for p in listar_perfis(conn) if p["perfil_id"] == perfil_id)


def listar_tokens_campanha(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.rotulo, t.nome, t.email, t.ativo, t.criado_em,
               t.quota_max, t.quota_used, p.slug, p.nome,
               left(t.token, 8) AS token_prefix
        FROM ctl.mcp_token t
        LEFT JOIN ctl.perfil p ON p.id = t.perfil_id
        WHERE t.campanha_id = %s::uuid
        ORDER BY t.criado_em DESC
        """,
        (campanha_id,),
    ).fetchall()
    return [
        {
            "rotulo": r[0],
            "nome": r[1],
            "email": r[2],
            "ativo": bool(r[3]),
            "criado_em": r[4].isoformat() if r[4] else None,
            "quota_max": r[5],
            "quota_used": int(r[6] or 0),
            "perfil_slug": r[7],
            "perfil_nome": r[8],
            "token_prefix": r[9],
        }
        for r in rows
    ]


def emitir_token_campanha(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    perfil: str,
    rotulo: str,
    actor_id: str,
    nome: str | None = None,
    email: str | None = None,
    quota_max: int | None = None,
) -> dict[str, Any]:
    perfil_id, perfil_slug = _perfil_por_slug_ou_id(conn, perfil)
    token = secrets.token_urlsafe(32)
    rot = (rotulo or "").strip()[:120] or f"mcp:{perfil_slug}"
    conn.execute(
        """
        INSERT INTO ctl.mcp_token
          (token, rotulo, nome, email, campanha_id, perfil_id, quota_max, quota_used, ativo)
        VALUES (%s, %s, %s, %s, %s::uuid, %s::uuid, %s, 0, TRUE)
        """,
        (
            token,
            rot,
            (nome or "").strip()[:120] or None,
            (email or "").strip().lower() or None,
            campanha_id,
            perfil_id,
            quota_max,
        ),
    )
    registrar_evento(
        conn,
        acao="token_emitir",
        usuario_id=actor_id,
        campanha_id=campanha_id,
        token_rotulo=rot,
        detalhe={"perfil": perfil_slug},
    )
    return {
        "token": token,
        "rotulo": rot,
        "perfil_slug": perfil_slug,
        "campanha_id": campanha_id,
        "quota_max": quota_max,
        "aviso": "Guarde o token agora — não será exibido de novo por completo.",
    }


def listar_eventos(
    conn: psycopg.Connection,
    *,
    campanha_id: str | None = None,
    usuario_id: str | None = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    limite = max(1, min(int(limite), 500))
    clauses = ["TRUE"]
    params: list[Any] = []
    if campanha_id:
        clauses.append("e.campanha_id = %s::uuid")
        params.append(campanha_id)
    if usuario_id:
        clauses.append("e.usuario_id = %s::uuid")
        params.append(usuario_id)
    params.append(limite)
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT e.id::text, e.ocorrido_em, e.acao, e.detalhe_json,
               e.usuario_id::text, u.email, e.campanha_id::text, c.nome,
               e.token_rotulo
        FROM ctl.evento_acesso e
        LEFT JOIN ctl.apura_usuario u ON u.id = e.usuario_id
        LEFT JOIN ctl.campanha c ON c.id = e.campanha_id
        WHERE {where}
        ORDER BY e.ocorrido_em DESC
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [
        {
            "id": r[0],
            "ocorrido_em": r[1].isoformat() if r[1] else None,
            "acao": r[2],
            "detalhe": r[3] if isinstance(r[3], dict) else (json.loads(r[3]) if r[3] else {}),
            "usuario_id": r[4],
            "usuario_email": r[5],
            "campanha_id": r[6],
            "campanha_nome": r[7],
            "token_rotulo": r[8],
        }
        for r in rows
    ]
