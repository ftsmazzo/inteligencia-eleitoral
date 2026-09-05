"""Store do módulo Mapa."""
from __future__ import annotations

import json
from typing import Any

import psycopg


def campanha_do_usuario(conn: psycopg.Connection, usuario_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT COALESCE(campanha_ativa_id, campanha_id)::text, email
        FROM ctl.apura_usuario
        WHERE id = %s::uuid
        """,
        (usuario_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def listar_municipios(conn: psycopg.Connection, uf: str = "AP") -> list[dict[str, Any]]:
    uf = (uf or "AP").strip().upper()[:2]
    rows = conn.execute(
        """
        SELECT g.cod_ibge, g.nome, g.sg_uf, g.lat, g.lng
        FROM ctl.municipio_geo g
        WHERE g.sg_uf = %s
        ORDER BY g.nome
        """,
        (uf,),
    ).fetchall()
    return [
        {
            "cod_ibge": int(r[0]),
            "nome": r[1],
            "sg_uf": r[2],
            "lat": float(r[3]),
            "lng": float(r[4]),
        }
        for r in rows
    ]


def listar_notas(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT n.id::text, n.cod_ibge, COALESCE(g.nome, n.cod_ibge::text), n.texto,
               n.atualizado_em::text, n.atualizado_por::text
        FROM ctl.mapa_nota n
        LEFT JOIN ctl.municipio_geo g ON g.cod_ibge = n.cod_ibge
        WHERE n.campanha_id = %s::uuid
        ORDER BY g.nome NULLS LAST
        """,
        (campanha_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "cod_ibge": int(r[1]),
            "nome": r[2],
            "texto": r[3] or "",
            "atualizado_em": r[4],
            "atualizado_por": r[5],
        }
        for r in rows
    ]


def upsert_nota(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    cod_ibge: int,
    texto: str,
    usuario_id: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO ctl.mapa_nota (campanha_id, cod_ibge, texto, atualizado_por, atualizado_em)
        VALUES (%s::uuid, %s, %s, %s::uuid, now())
        ON CONFLICT (campanha_id, cod_ibge) DO UPDATE SET
          texto = EXCLUDED.texto,
          atualizado_por = EXCLUDED.atualizado_por,
          atualizado_em = now()
        RETURNING id::text, cod_ibge, texto, atualizado_em::text
        """,
        (campanha_id, cod_ibge, (texto or "")[:20000], usuario_id),
    ).fetchone()
    nome_row = conn.execute(
        "SELECT nome FROM ctl.municipio_geo WHERE cod_ibge = %s",
        (cod_ibge,),
    ).fetchone()
    return {
        "id": row[0],
        "cod_ibge": int(row[1]),
        "nome": nome_row[0] if nome_row else str(cod_ibge),
        "texto": row[2] or "",
        "atualizado_em": row[3],
    }


def apagar_nota(conn: psycopg.Connection, *, campanha_id: str, cod_ibge: int) -> bool:
    cur = conn.execute(
        "DELETE FROM ctl.mapa_nota WHERE campanha_id = %s::uuid AND cod_ibge = %s",
        (campanha_id, cod_ibge),
    )
    return (cur.rowcount or 0) > 0


def listar_caravanas(conn: psycopg.Connection, campanha_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id::text, nome, pontos_json, rota_geojson, atualizado_em::text
        FROM ctl.mapa_caravana
        WHERE campanha_id = %s::uuid
        ORDER BY atualizado_em DESC
        """,
        (campanha_id,),
    ).fetchall()
    out = []
    for r in rows:
        pontos = r[2]
        if isinstance(pontos, str):
            pontos = json.loads(pontos)
        rota = r[3]
        if isinstance(rota, str):
            rota = json.loads(rota)
        out.append(
            {
                "id": r[0],
                "nome": r[1],
                "pontos": pontos or [],
                "rota_geojson": rota,
                "atualizado_em": r[4],
            }
        )
    return out


def salvar_caravana(
    conn: psycopg.Connection,
    *,
    campanha_id: str,
    nome: str,
    pontos: list[dict[str, Any]],
    rota_geojson: Any = None,
    usuario_id: str | None = None,
    caravana_id: str | None = None,
) -> dict[str, Any]:
    pontos_json = json.dumps(pontos or [], ensure_ascii=False)
    rota_json = json.dumps(rota_geojson, ensure_ascii=False) if rota_geojson is not None else None
    if caravana_id:
        row = conn.execute(
            """
            UPDATE ctl.mapa_caravana
            SET nome = %s, pontos_json = %s::jsonb,
                rota_geojson = COALESCE(%s::jsonb, rota_geojson),
                atualizado_em = now()
            WHERE id = %s::uuid AND campanha_id = %s::uuid
            RETURNING id::text, nome, pontos_json, rota_geojson, atualizado_em::text
            """,
            (nome[:200], pontos_json, rota_json, caravana_id, campanha_id),
        ).fetchone()
        if not row:
            raise ValueError("caravana não encontrada")
    else:
        row = conn.execute(
            """
            INSERT INTO ctl.mapa_caravana
              (campanha_id, nome, pontos_json, rota_geojson, criado_por)
            VALUES (%s::uuid, %s, %s::jsonb, %s::jsonb, %s::uuid)
            RETURNING id::text, nome, pontos_json, rota_geojson, atualizado_em::text
            """,
            (campanha_id, nome[:200] or "Carreata", pontos_json, rota_json, usuario_id),
        ).fetchone()
    pontos_out = row[2]
    if isinstance(pontos_out, str):
        pontos_out = json.loads(pontos_out)
    rota_out = row[3]
    if isinstance(rota_out, str):
        rota_out = json.loads(rota_out)
    return {
        "id": row[0],
        "nome": row[1],
        "pontos": pontos_out or [],
        "rota_geojson": rota_out,
        "atualizado_em": row[4],
    }


def apagar_caravana(conn: psycopg.Connection, *, campanha_id: str, caravana_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM ctl.mapa_caravana WHERE id = %s::uuid AND campanha_id = %s::uuid",
        (caravana_id, campanha_id),
    )
    return (cur.rowcount or 0) > 0
