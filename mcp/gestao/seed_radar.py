"""Seed Radar a partir do escopo Gestão + memória + planos (sq exato). Aditivo — nunca apaga."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import psycopg

from gestao import memoria
from gestao import temas_plano
from gestao.store import get_status
from radar import store as radar_store
from radar.collect import UF_NOME

_SEED_DIR = Path(__file__).resolve().parents[1] / "seed"


def _upsert_documento_acervo(conn: psycopg.Connection, doc: dict[str, Any]) -> None:
    """Mesma lógica de scripts/carregar_acervo_planos.py::carregar_db — upsert por sha256."""
    dig = doc.get("sha256")
    if not dig:
        return
    row = conn.execute(
        "SELECT id FROM acervo.documento WHERE sha256 = %s AND tipo = %s",
        (dig, doc["tipo"]),
    ).fetchone()
    meta_json = json.dumps(doc.get("meta") or {}, ensure_ascii=False)
    if row:
        doc_id = row[0]
        conn.execute("DELETE FROM acervo.chunk WHERE documento_id = %s", (doc_id,))
        conn.execute(
            """
            UPDATE acervo.documento SET
              titulo=%s, descricao=%s, nivel=%s, ano_eleicao=%s,
              vigencia_inicio=%s, vigencia_fim=%s, escopo=%s,
              sg_uf=%s, nm_candidato=%s, cargo=%s, tags=%s, fonte_orgao=%s,
              id_base_raw=%s, meta=%s, ativo=true, atualizado_em=now()
            WHERE id=%s
            """,
            (
                doc["titulo"], doc.get("descricao"), doc.get("nivel"), doc.get("ano_eleicao"),
                doc.get("vigencia_inicio"), doc.get("vigencia_fim"), doc.get("escopo"),
                doc.get("sg_uf"), doc.get("nm_candidato"), doc.get("cargo"), doc.get("tags"),
                doc.get("fonte_orgao"), doc.get("id_base_raw"), meta_json, doc_id,
            ),
        )
    else:
        doc_id = uuid.uuid4()
        conn.execute(
            """
            INSERT INTO acervo.documento (
              id, tipo, titulo, descricao, nivel, ano_eleicao,
              vigencia_inicio, vigencia_fim, escopo, sg_uf, sg_partido,
              nm_candidato, cargo, tags, fonte_orgao, sha256, id_base_raw, meta
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                doc_id, doc["tipo"], doc["titulo"], doc.get("descricao"), doc.get("nivel"),
                doc.get("ano_eleicao"), doc.get("vigencia_inicio"), doc.get("vigencia_fim"),
                doc.get("escopo"), doc.get("sg_uf"), doc.get("sg_partido"), doc.get("nm_candidato"),
                doc.get("cargo"), doc.get("tags"), doc.get("fonte_orgao"), dig, doc.get("id_base_raw"),
                meta_json,
            ),
        )
    chunks = doc.get("chunks") or []
    if chunks:
        conn.executemany(
            """
            INSERT INTO acervo.chunk (documento_id, ord, secao, texto, token_count)
            VALUES (%s,%s,%s,%s,%s)
            """,
            [
                (doc_id, ch["ord"], ch.get("secao", ""), ch["texto"], max(1, len(ch["texto"]) // 4))
                for ch in chunks
            ],
        )


def _garantir_planos_uf(
    conn: psycopg.Connection,
    *,
    uf: str | None,
    cargo: str | None,
    ano_eleicao: int | None,
) -> int:
    """Auto-carrega planos de governo do MESMO pleito (uf+cargo+ano) a partir do seed
    empacotado em mcp/seed/, só se o acervo ainda não tiver nenhum documento desse
    pleito. Idempotente (upsert por sha256) — nunca duplica, nunca mexe em outro pleito."""
    if not uf or not cargo or not ano_eleicao:
        return 0
    try:
        n = conn.execute(
            """
            SELECT count(*) FROM acervo.documento
            WHERE tipo='plano_governo' AND lower(cargo)=lower(%s)
              AND upper(sg_uf)=upper(%s) AND ano_eleicao=%s
            """,
            (cargo, uf, ano_eleicao),
        ).fetchone()
        if n and int(n[0] or 0) > 0:
            return 0
    except Exception:
        return 0
    seed_path = _SEED_DIR / f"acervo_planos_{ano_eleicao}.jsonl"
    if not seed_path.exists():
        return 0
    carregados = 0
    try:
        with seed_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if doc.get("tipo") != "plano_governo":
                    continue
                if (doc.get("cargo") or "").lower() != cargo.lower():
                    continue
                if (doc.get("sg_uf") or "").upper() != uf.upper():
                    continue
                _upsert_documento_acervo(conn, doc)
                carregados += 1
    except Exception:
        return carregados
    return carregados

_IG_LIXO = {
    "channel",
    "share",
    "instagram",
    "www",
    "p",
    "reel",
    "reels",
    "tv",
    "stories",
    "explore",
    "accounts",
    "direct",
    "about",
}


def _ig_ok(h: str | None) -> str | None:
    if not h:
        return None
    clean = h.strip().lstrip("@").split("?")[0].strip()
    if not clean or clean.lower() in _IG_LIXO:
        return None
    if len(clean) < 2 or "/" in clean or " " in clean:
        return None
    return clean


def _igs_limpos(raw: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for h in raw or []:
        ok = _ig_ok(str(h) if h else None)
        if not ok:
            continue
        key = ok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ok)
    return out


def _existe(
    existentes: list[dict[str, Any]],
    *,
    nome: str | None = None,
    handle: str | None = None,
) -> bool:
    if handle:
        h = handle.lower().lstrip("@")
        if any((a.get("handle_ig") or "").lower() == h for a in existentes):
            return True
    if nome:
        nl = nome.strip().lower()
        if any((a.get("nome") or "").strip().lower() == nl for a in existentes):
            return True
    return False


def _norm(s: str | None) -> str:
    import unicodedata

    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _pode_criar(
    conn: psycopg.Connection,
    campanha_id: str,
    existentes: list[dict[str, Any]],
    *,
    kind: str,
    nome: str | None = None,
    handle: str | None = None,
) -> bool:
    """Só cria se não existe ainda E o usuário não apagou esse alvo antes (bloqueio permanente)."""
    if _existe(existentes, nome=nome, handle=handle):
        return False
    if radar_store.esta_excluido(conn, campanha_id, kind, nome, handle):
        return False
    return True


def seed_radar_da_gestao(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any]:
    """Preenche Alvos a partir da Gestão. Sempre ADITIVO — nunca apaga o que já existe
    (inclusive alvos cadastrados à mão, como Instagram oficial validado manualmente)."""
    st = get_status(conn, campanha_id)
    if not st.get("nm_urna") and not st.get("nm_candidato"):
        raise ValueError("Escopo sem candidato")

    nome = st.get("nm_urna") or st.get("nm_candidato")
    uf = st.get("sg_uf")
    uf_nome = UF_NOME.get((uf or "").strip().upper(), "") or (uf or "")
    cargo = st.get("cargo_label") or ""
    partido = st.get("sg_partido")
    sq = st.get("sq_candidato")

    try:
        conn.execute(
            """
            INSERT INTO ctl.radar_config (campanha_id, candidato_nome, uf, cargo, atualizado_em)
            VALUES (%s::uuid, %s, %s, %s, now())
            ON CONFLICT (campanha_id) DO UPDATE SET
              candidato_nome = EXCLUDED.candidato_nome,
              uf = EXCLUDED.uf,
              cargo = EXCLUDED.cargo,
              atualizado_em = now()
            """,
            (campanha_id, nome, uf, cargo),
        )
    except Exception:
        pass

    radar_store.ensure_eixos(conn, campanha_id)
    added = 0
    stats = {"pessoa": 0, "adversario": 0, "perfil": 0, "tema": 0, "eixos_kw": 0}

    existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
    if _pode_criar(conn, campanha_id, existentes, kind="pessoa", nome=nome):
        radar_store.upsert_alvo(
            conn,
            campanha_id,
            kind="pessoa",
            nome=nome,
            query_news=f"{nome} {uf_nome} {cargo}".strip(),
            handle_ig=None,
            is_own=False,
            papel="proprio",
            prioridade=1,
            notas=f"{partido or ''} · monitorado (candidato do escopo)".strip(" ·"),
        )
        added += 1
        stats["pessoa"] += 1

    pessoas: list[dict[str, Any]] = []
    # Só o bloco base_redes MAIS RECENTE — blocos antigos podem ter sido gerados
    # antes de uma correção de escopo e trazer papel="proprio" para a pessoa errada
    # (ex.: escopo apontava para outro candidato de nome parecido antes do ajuste).
    blocos = memoria.listar(conn, campanha_id, tipo="base_redes", limite=1)
    for b in blocos:
        meta = b.get("meta") or {}
        pessoas.extend(meta.get("pessoas") or [])

    # adversários com sq_candidato (para casar plano de governo com precisão)
    adversarios_sq: list[dict[str, Any]] = []
    nome_norm = _norm(nome)

    for p in pessoas:
        papel = p.get("papel") or "adversario"
        nm = (p.get("nm_urna") or "").strip()
        sq_p = p.get("sq_candidato")
        igs = _igs_limpos(p.get("ig"))
        # Nunca confia cegamente em papel="proprio" do bloco: o que decide se é o
        # PRÓPRIO candidato é o nome bater com o escopo atual — não o rótulo salvo
        # (blocos antigos podem ter sido gerados com escopo errado/desatualizado
        # e marcar outra pessoa como "proprio", duplicando o candidato na tela).
        proprio = (_norm(nm) == nome_norm) if nm else (papel == "proprio")

        if not proprio and nm and nm != nome:
            adversarios_sq.append({"nome": nm, "sq_candidato": sq_p})
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if _pode_criar(conn, campanha_id, existentes, kind="adversario", nome=nm):
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="adversario",
                    nome=nm,
                    query_news=f"{nm} {uf_nome}".strip(),
                    handle_ig=None,
                    is_own=False,
                    papel="adversario",
                    prioridade=2,
                    notas=(p.get("sg_partido") or ""),
                )
                added += 1
                stats["adversario"] += 1

        for h in igs:
            existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
            if not _pode_criar(conn, campanha_id, existentes, kind="perfil", handle=h):
                continue
            radar_store.upsert_alvo(
                conn,
                campanha_id,
                kind="perfil",
                nome=f"@{h}" + (" (oficial)" if proprio else f" ({nm})" if nm else ""),
                query_news="" if proprio else f"{nm} {uf_nome}".strip(),
                handle_ig=h,
                is_own=proprio,
                papel="proprio" if proprio else "adversario",
                prioridade=1 if proprio else 2,
            )
            added += 1
            stats["perfil"] += 1

    # fallback: adversários citados na nominata mesmo sem IG na base_redes
    if not adversarios_sq:
        conc = memoria.listar(conn, campanha_id, tipo="base_concorrentes", limite=1)
        if conc:
            linhas = [
                ln.strip()[2:]
                for ln in (conc[0].get("corpo") or "").splitlines()
                if ln.strip().startswith("- ")
            ]
            for ln in linhas[:8]:
                nome_adv = ln.split("·")[0].strip()
                if not nome_adv or nome_adv == nome:
                    continue
                adversarios_sq.append({"nome": nome_adv, "sq_candidato": None})
                existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
                if not _pode_criar(conn, campanha_id, existentes, kind="adversario", nome=nome_adv):
                    continue
                radar_store.upsert_alvo(
                    conn,
                    campanha_id,
                    kind="adversario",
                    nome=nome_adv,
                    query_news=f"{nome_adv} {uf_nome}",
                    handle_ig=None,
                    is_own=False,
                    papel="adversario",
                    prioridade=2,
                )
                added += 1
                stats["adversario"] += 1

    # Temas + keywords a partir do plano de governo (sq exato, com fallback por nome
    # restrito ao mesmo pleito — ver temas_plano.py).
    ano_eleicao = st.get("ano_ref") or 2026
    cargo_key = (cargo or "").strip().lower() or None
    try:
        stats["planos_carregados"] = _garantir_planos_uf(
            conn, uf=uf, cargo=cargo_key, ano_eleicao=ano_eleicao
        )
    except Exception:
        stats["planos_carregados"] = 0

    extracao: dict[str, Any] = {
        "temas_proprio": [],
        "temas_adversario": [],
        "keywords_eixos": {},
        "plano_chars": 0,
    }
    try:
        extracao = temas_plano.extrair_campanha(
            conn,
            campanha_id=campanha_id,
            uf=uf,
            sq_candidato=str(sq) if sq else None,
            nm_candidato=nome,
            adversarios=adversarios_sq,
            cargo=cargo_key,
            ano_eleicao=ano_eleicao,
        )
    except Exception:
        pass
    try:
        stats["eixos_kw"] = radar_store.merge_eixo_keywords(
            conn, campanha_id, extracao.get("keywords_eixos") or {}
        )
    except Exception:
        stats["eixos_kw"] = 0

    for tm in list(extracao.get("temas_proprio") or []) + list(
        extracao.get("temas_adversario") or []
    ):
        nm_t = (tm.get("nome") or "").strip()
        if not nm_t:
            continue
        existentes = radar_store.list_alvos(conn, campanha_id, ativo_only=False)
        if not _pode_criar(conn, campanha_id, existentes, kind="tema", nome=nm_t):
            continue
        try:
            radar_store.upsert_alvo(
                conn,
                campanha_id,
                kind="tema",
                nome=nm_t,
                query_news=(tm.get("query_news") or nm_t)[:300],
                handle_ig=None,
                is_own=False,
                papel=tm.get("papel") or "tema",
                prioridade=4,
                notas=(tm.get("eixo") or "")[:200],
            )
            added += 1
            stats["tema"] += 1
        except Exception:
            continue

    return {
        "ok": True,
        "added": added,
        "candidato": nome,
        "partido": partido,
        "uf": uf,
        "stats": stats,
        "plano_chars": extracao.get("plano_chars") or 0,
        "plano_proprio_encontrado": bool(extracao.get("plano_chars")),
        "plano_diag": extracao.get("diag") or {},
    }
