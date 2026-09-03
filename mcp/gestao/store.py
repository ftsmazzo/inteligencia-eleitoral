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
               escopo_json, atualizado_em,
               COALESCE(equipe_liberada, false)
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
        "equipe_liberada": bool(row[13]),
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
    # quem inicia vira coordenador
    try:
        conn.execute(
            "UPDATE ctl.apura_usuario SET papel = 'coordenador' WHERE id = %s::uuid",
            (usuario_id,),
        )
    except Exception:
        pass
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
    from gestao import documento

    uf = (sg_uf or "").strip().upper()
    if cd_cargo == 1:
        uf = uf if uf in UFS else None
    elif uf not in UFS:
        raise ValueError("UF inválida")
    if cd_cargo not in {c["cd_cargo"] for c in CARGOS}:
        raise ValueError("Cargo fora do recorte Gestão")
    if ano_ref != 2026:
        raise ValueError("Gestão Sprint 1: apenas ano 2026")

    # Documento canônico no banco — não confiar só no texto digitado na UI
    doc = documento.por_sq(conn, ano=ano_ref, sq_candidato=int(sq_candidato))
    if not doc:
        raise ValueError("Candidato inexistente na nominata deste ano/sq — selecione de novo na lista")
    if int(doc["cd_cargo"]) != int(cd_cargo):
        raise ValueError("sq não corresponde ao cargo escolhido")
    if uf and doc.get("sg_uf") and doc["sg_uf"] != uf and cd_cargo != 1:
        raise ValueError("sq não corresponde à UF escolhida")

    nm_candidato = doc["nm_candidato"] or nm_candidato
    nm_urna = doc["nm_urna"] or nm_urna
    sg_partido = doc["sg_partido"] or sg_partido
    nr_candidato = doc["nr_candidato"] if doc["nr_candidato"] is not None else nr_candidato

    extra = dict(escopo_json or {})
    extra["documento"] = {
        "sq_candidato": doc["sq_candidato"],
        "nm_urna": doc["nm_urna"],
        "nm_candidato": doc["nm_candidato"],
        "sg_partido": doc["sg_partido"],
        "nr_candidato": doc["nr_candidato"],
        "fonte": "eleicao.candidatura",
    }
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


def resetar_gestao(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    """Apaga memória/radar da campanha e zera escopo — recomeço limpo."""
    conn.execute("DELETE FROM ctl.campanha_memoria WHERE campanha_id = %s::uuid", (campanha_id,))
    try:
        conn.execute("DELETE FROM ctl.radar_item WHERE campanha_id = %s::uuid", (campanha_id,))
    except Exception:
        pass
    try:
        conn.execute("DELETE FROM ctl.radar_alvo WHERE campanha_id = %s::uuid", (campanha_id,))
    except Exception:
        pass
    try:
        conn.execute("DELETE FROM ctl.radar_run WHERE campanha_id = %s::uuid", (campanha_id,))
    except Exception:
        pass
    try:
        conn.execute("DELETE FROM ctl.radar_config WHERE campanha_id = %s::uuid", (campanha_id,))
    except Exception:
        pass
    conn.execute(
        """
        UPDATE ctl.campanha
        SET ano_ref = NULL,
            cd_cargo = NULL,
            sg_uf = NULL,
            sq_candidato = NULL,
            nm_candidato = NULL,
            nm_urna = NULL,
            sg_partido = NULL,
            nr_candidato = NULL,
            escopo_json = '{}'::jsonb,
            ambiente_status = 'rascunho',
            equipe_liberada = FALSE,
            atualizado_em = now()
        WHERE id = %s::uuid
        """,
        (campanha_id,),
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
        if not row or row[0] is None or row[1] is None or row[3] is None:
            raise ValueError("Defina o escopo (ano, cargo, candidato) antes de marcar pronto")
        if int(row[1]) != 1 and not row[2]:
            raise ValueError("UF obrigatória para este cargo")
    conn.execute(
        """
        UPDATE ctl.campanha
        SET ambiente_status = %s, atualizado_em = now()
        WHERE id = %s::uuid
        """,
        (st, campanha_id),
    )
    return get_status(conn, campanha_id)


def liberar_equipe(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    st = get_status(conn, campanha_id)
    if not st.get("sq_candidato"):
        raise ValueError("Salve o escopo antes de liberar a equipe")
    conn.execute(
        """
        UPDATE ctl.campanha
        SET ambiente_status = 'pronto',
            equipe_liberada = TRUE,
            atualizado_em = now()
        WHERE id = %s::uuid
        """,
        (campanha_id,),
    )
    return get_status(conn, campanha_id)


def papel_usuario(conn: psycopg.Connection, usuario_id: str) -> str:
    try:
        row = conn.execute(
            "SELECT COALESCE(papel, 'equipe') FROM ctl.apura_usuario WHERE id = %s::uuid",
            (usuario_id,),
        ).fetchone()
        return (row[0] if row else "equipe") or "equipe"
    except Exception:
        return "equipe"
