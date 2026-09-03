"""Persistência do escopo de campanha (Gestão)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import psycopg

STATUS_OK = ("legado", "rascunho", "configurando", "pronto")
STATUS_SET = ("rascunho", "configurando", "pronto")

CARGOS = (
    {"key": "presidente", "label": "Presidente", "cd_cargo": 1},
    {"key": "governador", "label": "Governador", "cd_cargo": 3},
    {"key": "senador", "label": "Senador", "cd_cargo": 5},
    {"key": "deputado_federal", "label": "Deputado federal", "cd_cargo": 6},
    {"key": "deputado_estadual", "label": "Deputado estadual", "cd_cargo": 7},
)

UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)


def campanha_do_usuario(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT u.campanha_id::text, c.nome
        FROM ctl.apura_usuario u
        JOIN ctl.campanha c ON c.id = u.campanha_id
        WHERE u.id = %s::uuid AND u.ativo IS TRUE
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def _slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (nome or "").lower()).strip("-")
    return (s or "campanha")[:80]


def get_status(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id::text, nome, ambiente_status, ano_ref, cd_cargo, sg_uf,
               sq_candidato, nm_candidato, nm_urna, sg_partido, nr_candidato,
               escopo_json, atualizado_em
        FROM ctl.campanha
        WHERE id = %s::uuid
        """,
        (campanha_id,),
    ).fetchone()
    if not row:
        return {}
    escopo = row[11] if isinstance(row[11], dict) else (json.loads(row[11]) if row[11] else {})
    mem = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE tipo = 'perfil_eleitor')::int,
          COUNT(*) FILTER (WHERE tipo LIKE 'dossie%%' OR tipo = 'dossie')::int,
          COUNT(*)::int
        FROM ctl.campanha_memoria
        WHERE campanha_id = %s::uuid
        """,
        (campanha_id,),
    ).fetchone()
    cargo_label = next((c["label"] for c in CARGOS if c["cd_cargo"] == row[4]), None)
    return {
        "campanha_id": row[0],
        "campanha_nome": row[1],
        "ambiente_status": row[2] or "legado",
        "ano_ref": row[3],
        "cd_cargo": row[4],
        "cargo_label": cargo_label,
        "sg_uf": row[5],
        "sq_candidato": row[6],
        "nm_candidato": row[7],
        "nm_urna": row[8],
        "sg_partido": row[9],
        "nr_candidato": row[10],
        "escopo_json": escopo or {},
        "atualizado_em": row[12].isoformat() if row[12] else None,
        "tem_perfil": bool(mem and mem[0]),
        "tem_dossie": bool(mem and mem[1]),
        "memoria_blocos": int(mem[2] or 0) if mem else 0,
        "cargos": list(CARGOS),
        "ufs": list(UFS),
    }


def iniciar(
    conn: psycopg.Connection,
    usuario_id: str,
    nome: str | None = None,
) -> dict[str, Any]:
    cur = campanha_do_usuario(conn, usuario_id)
    if not cur:
        raise ValueError("Usuário sem campanha")
    cid, cnome = cur
    novo_nome = (nome or "").strip()
    if novo_nome and novo_nome != cnome:
        # Nova campanha dedicada à gestão
        slug = _slug(novo_nome)
        base = slug
        n = 1
        while conn.execute(
            "SELECT 1 FROM ctl.campanha WHERE nome = %s", (slug,)
        ).fetchone():
            n += 1
            slug = f"{base}-{n}"
        nid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO ctl.campanha (id, nome, ativo, ambiente_status, atualizado_em)
            VALUES (%s::uuid, %s, TRUE, 'rascunho', now())
            """,
            (nid, slug),
        )
        conn.execute(
            "UPDATE ctl.apura_usuario SET campanha_id = %s::uuid WHERE id = %s::uuid",
            (nid, usuario_id),
        )
        cid = nid
    else:
        conn.execute(
            """
            UPDATE ctl.campanha
            SET ambiente_status = CASE
                  WHEN ambiente_status = 'legado' THEN 'rascunho'
                  ELSE ambiente_status
                END,
                atualizado_em = now()
            WHERE id = %s::uuid
            """,
            (cid,),
        )
    return get_status(conn, cid)


def salvar_escopo(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    ano_ref: int,
    cd_cargo: int,
    sg_uf: str,
    sq_candidato: int,
    nm_candidato: str,
    nm_urna: str,
    sg_partido: str | None,
    nr_candidato: int | None,
    escopo_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    uf = (sg_uf or "").strip().upper()
    if cd_cargo == 1:
        uf = uf if uf in UFS else None
    elif uf not in UFS:
        raise ValueError("UF inválida")
    if cd_cargo not in {c["cd_cargo"] for c in CARGOS}:
        raise ValueError("Cargo fora do recorte Gestão")
    if ano_ref != 2026:
        raise ValueError("Gestão Sprint 1: apenas ano 2026")
    extra = escopo_json or {}
    conn.execute(
        """
        UPDATE ctl.campanha
        SET ano_ref = %s,
            cd_cargo = %s,
            sg_uf = %s,
            sq_candidato = %s,
            nm_candidato = %s,
            nm_urna = %s,
            sg_partido = %s,
            nr_candidato = %s,
            escopo_json = COALESCE(escopo_json, '{}'::jsonb) || %s::jsonb,
            ambiente_status = CASE
              WHEN ambiente_status IN ('legado', 'rascunho') THEN 'configurando'
              ELSE ambiente_status
            END,
            atualizado_em = now()
        WHERE id = %s::uuid
        """,
        (
            ano_ref,
            cd_cargo,
            uf,
            sq_candidato,
            (nm_candidato or "").strip()[:200],
            (nm_urna or "").strip()[:120],
            (sg_partido or "").strip().upper()[:20] or None,
            nr_candidato,
            json.dumps(extra, ensure_ascii=False),
            campanha_id,
        ),
    )
    return get_status(conn, campanha_id)


def set_ambiente(conn: psycopg.Connection, campanha_id: str, status: str) -> dict[str, Any]:
    st = (status or "").strip().lower()
    if st not in STATUS_SET:
        raise ValueError("Status inválido (use rascunho|configurando|pronto)")
    if st == "pronto":
        row = conn.execute(
            """
            SELECT ano_ref, cd_cargo, sg_uf, sq_candidato
            FROM ctl.campanha WHERE id = %s::uuid
            """,
            (campanha_id,),
        ).fetchone()
        if not row or not all(row):
            raise ValueError("Defina o escopo (ano, cargo, UF, candidato) antes de marcar pronto")
    conn.execute(
        """
        UPDATE ctl.campanha
        SET ambiente_status = %s, atualizado_em = now()
        WHERE id = %s::uuid
        """,
        (st, campanha_id),
    )
    return get_status(conn, campanha_id)
