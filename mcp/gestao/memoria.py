"""Memória indexada da campanha (ctl.campanha_memoria)."""
from __future__ import annotations

import json
import re
from typing import Any

import psycopg

# Ordem no prompt: identidade/estratégia antes de blocos de urna genéricos.
_ORDEM_TIPO = """
              CASE tipo
                WHEN 'estrategias' THEN 0
                WHEN 'dossie' THEN 1
                WHEN 'perfil_eleitor' THEN 2
                WHEN 'base_concorrentes' THEN 3
                WHEN 'base_trajetoria' THEN 4
                WHEN 'base_votos' THEN 5
                WHEN 'base_mapa_cargo' THEN 6
                WHEN 'base_prefeitos' THEN 7
                WHEN 'base_ficha_uf' THEN 8
                WHEN 'base_redes' THEN 9
                WHEN 'base_eleitorado' THEN 10
                ELSE CASE WHEN tipo LIKE 'dossie%%' THEN 1 ELSE 20 END
              END
"""

_RIVAL_LABEL = re.compile(
    r"(?:rival|advers[aá]rio[sa]?|oponente|concorrente\s+principal)"
    r"\s*[:\-–]\s*(.+)$",
    re.I,
)


def limpar_tipos(conn: psycopg.Connection, campanha_id: str, tipos: list[str]) -> None:
    if not tipos:
        return
    conn.execute(
        """
        DELETE FROM ctl.campanha_memoria
        WHERE campanha_id = %s::uuid AND tipo = ANY(%s)
        """,
        (campanha_id, tipos),
    )


def upsert_bloco(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    tipo: str,
    titulo: str,
    corpo: str,
    fonte: str = "",
    nivel: str = "indicio",
    meta: dict[str, Any] | None = None,
) -> str:
    row = conn.execute(
        """
        INSERT INTO ctl.campanha_memoria
          (campanha_id, tipo, titulo, corpo, fonte, nivel, meta_json)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id::text
        """,
        (
            campanha_id,
            tipo,
            (titulo or "")[:300],
            corpo or "",
            fonte or "",
            nivel or "indicio",
            json.dumps(meta or {}, ensure_ascii=False),
        ),
    ).fetchone()
    return row[0] if row else ""


def listar(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    tipo: str | None = None,
    query: str | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limite or 50), 200))
    q = (query or "").strip()
    like = f"%{q}%" if q else None
    if tipo and like:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid AND tipo = %s
              AND (titulo ILIKE %s OR corpo ILIKE %s)
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, tipo, like, like, lim),
        ).fetchall()
    elif like:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid
              AND (titulo ILIKE %s OR corpo ILIKE %s)
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, like, like, lim),
        ).fetchall()
    elif tipo:
        rows = conn.execute(
            """
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid AND tipo = %s
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (campanha_id, tipo, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT id::text, tipo, titulo, corpo, fonte, nivel, meta_json, criado_em
            FROM ctl.campanha_memoria
            WHERE campanha_id = %s::uuid
            ORDER BY
              {_ORDEM_TIPO},
              criado_em DESC
            LIMIT %s
            """,
            (campanha_id, lim),
        ).fetchall()
    out = []
    for r in rows:
        meta = r[6] if isinstance(r[6], dict) else (json.loads(r[6]) if r[6] else {})
        out.append(
            {
                "id": r[0],
                "tipo": r[1],
                "titulo": r[2],
                "corpo": r[3],
                "fonte": r[4],
                "nivel": r[5],
                "meta": meta,
                "criado_em": r[7].isoformat() if r[7] else None,
            }
        )
    return out


def _norm_nome(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _add_nome(dest: list[str], seen: set[str], nome: str, *, limite: int = 8, nosso: str = "") -> None:
    nm = (nome or "").strip()
    if not nm or nm.startswith("@"):
        return
    nm = re.split(r"\s*[·|]\s*", nm)[0].strip()
    nm = re.sub(r"\s+n[ºo°].*$", "", nm, flags=re.I).strip()
    key = _norm_nome(nm)
    if len(key) < 3 or key in seen or len(dest) >= limite:
        return
    if nosso:
        n_key = _norm_nome(nosso)
        # evita listar o próprio candidato como "rival" (ex.: Carlos Cley vs Cley)
        if key == n_key or key in n_key or n_key in key:
            return
        tok_n = set(n_key.split())
        tok = set(key.split())
        if tok and tok <= tok_n:
            return
    seen.add(key)
    dest.append(nm)


def _rivais_de_radar(
    conn: psycopg.Connection, campanha_id: str, *, nosso: str = ""
) -> tuple[list[str], list[str]]:
    rivais: list[str] = []
    handles: list[str] = []
    seen_r: set[str] = set()
    seen_h: set[str] = set()
    try:
        from radar import store as radar_store

        alvos = radar_store.list_alvos(conn, campanha_id, ativo_only=True)
    except Exception:
        return rivais, handles
    for a in alvos:
        papel = (a.get("papel") or "").lower()
        is_own = bool(a.get("is_own")) or papel == "proprio"
        h = (a.get("handle_ig") or "").strip().lstrip("@")
        if h and h.lower() not in seen_h:
            seen_h.add(h.lower())
            tag = "nosso" if is_own else "rival"
            handles.append(f"@{h} ({tag})")
        if is_own:
            continue
        if papel == "adversario" or a.get("kind") in ("adversario", "pessoa"):
            _add_nome(rivais, seen_r, a.get("nome") or "", nosso=nosso)
    return rivais, handles


def _rivais_de_redes(conn: psycopg.Connection, campanha_id: str, nosso: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = {_norm_nome(nosso)} if nosso else set()
    for b in listar(conn, campanha_id, tipo="base_redes", limite=1):
        for p in (b.get("meta") or {}).get("pessoas") or []:
            if (p.get("papel") or "").lower() == "proprio":
                continue
            nm = (p.get("nm_urna") or p.get("nome") or "").strip()
            _add_nome(out, seen, nm, nosso=nosso)
    return out


def _rivais_de_rotulos(conn: psycopg.Connection, campanha_id: str, *, nosso: str = "") -> list[str]:
    """Extrai rivais rotulados em dossiê / estratégias (linha ou meta)."""
    out: list[str] = []
    seen: set[str] = {_norm_nome(nosso)} if nosso else set()
    near = re.compile(
        r"(?:rival|advers[aá]rio[sa]?|oponente)[^\n]{0,48}?"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁ-ú''\-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁ-ú''\-]+){0,3})",
        re.I,
    )

    def _scan_blob(blob: str) -> None:
        for ln in (blob or "").splitlines():
            m = _RIVAL_LABEL.search(ln.strip())
            if m:
                _add_nome(out, seen, m.group(1), limite=6, nosso=nosso)
                continue
            for m2 in near.finditer(ln):
                _add_nome(out, seen, m2.group(1), limite=6, nosso=nosso)

    for tipo in ("estrategias", "dossie"):
        for b in listar(conn, campanha_id, tipo=tipo, limite=5):
            _scan_blob(f"{b.get('titulo') or ''}\n{b.get('corpo') or ''}")
            meta = b.get("meta") or {}
            for key in ("rival", "rivais", "adversario", "adversarios"):
                val = meta.get(key)
                if isinstance(val, str):
                    _add_nome(out, seen, val, nosso=nosso)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            _add_nome(out, seen, item, nosso=nosso)
                        elif isinstance(item, dict):
                            _add_nome(
                                out,
                                seen,
                                item.get("nome") or item.get("nm_urna") or "",
                                nosso=nosso,
                            )
    for b in listar(conn, campanha_id, limite=40):
        if not (b.get("tipo") or "").startswith("dossie"):
            continue
        if b.get("tipo") == "dossie":
            continue
        _scan_blob(f"{b.get('titulo') or ''}\n{b.get('corpo') or ''}")
    return out


def texto_alvos_para_apura(
    conn: psycopg.Connection,
    campanha_id: str,
    status: dict[str, Any] | None = None,
    radar_cfg: dict[str, Any] | None = None,
) -> str:
    """Card curto no topo: quem é 'nós' e quem é o rival canônico da campanha.

    Resolve o bug: 'nosso rival' NÃO pode ser o vice de urna antiga se o dossiê/Radar
    apontam outro nome (ex.: Furlan).
    """
    status = status or {}
    radar_cfg = radar_cfg or {}
    nosso = (
        status.get("nm_urna")
        or status.get("nm_candidato")
        or radar_cfg.get("candidato_nome")
        or ""
    ).strip()

    rivais: list[str] = []
    seen: set[str] = {_norm_nome(nosso)} if nosso else set()
    handles: list[str] = []

    for nm in _rivais_de_rotulos(conn, campanha_id, nosso=nosso):
        _add_nome(rivais, seen, nm, nosso=nosso)
    r_radar, h_radar = _rivais_de_radar(conn, campanha_id, nosso=nosso)
    for nm in r_radar:
        _add_nome(rivais, seen, nm, nosso=nosso)
    handles.extend(h_radar)
    for nm in _rivais_de_redes(conn, campanha_id, nosso):
        _add_nome(rivais, seen, nm, nosso=nosso)

    tem_estrategias = bool(listar(conn, campanha_id, tipo="estrategias", limite=1))
    tem_dossie = any(
        (b.get("tipo") or "").startswith("dossie") for b in listar(conn, campanha_id, limite=30)
    )

    linhas = [
        "IDENTIDADE DA CAMPANHA (uso interno do modelo — NÃO repetir este título ao usuário):",
        "Fale ao usuário só com: nosso candidato, rival, adversário + nomes próprios.",
    ]
    if nosso:
        linhas.append(f"- Nosso candidato: {nosso}")
    if rivais:
        linhas.append(
            "- Rival(is) de campanha (para \"nosso rival/adversário/eles\"): "
            + "; ".join(rivais[:6])
        )
    else:
        linhas.append(
            "- Rival(is) de campanha: ainda não nomeados no dossiê/Radar/estratégias — "
            "pergunte 1 nome ou leia o dossiê; NÃO invente a partir do vice/chapa de urna antiga."
        )
    if handles:
        seen_h: set[str] = set()
        uniq = []
        for h in handles:
            k = h.lower()
            if k not in seen_h:
                seen_h.add(k)
                uniq.append(h)
        linhas.append("- Handles / Radar (interno): " + ", ".join(uniq[:10]))
    linhas.append(
        f"- Memória: dossiê={'sim' if tem_dossie else 'não'} · "
        f"estratégias={'sim' if tem_estrategias else 'não (bloco tipo=estrategias ausente)'}"
    )
    linhas.append(
        "REGRA DURA (orquestrador): rival/adversário NÃO se define por nominata/votação antiga. "
        "Resolva o nome aqui (ou dossiê/estratégias/redes); só depois urna/clima/web SOBRE esse nome. "
        "base_concorrentes = lista histórica do cargo, não substitui o rival atual."
    )
    return "\n".join(linhas)


def texto_escopo_para_apura(
    status: dict[str, Any] | None,
    radar_cfg: dict[str, Any] | None = None,
) -> str:
    """Bloco fixo de identidade da campanha — sempre no topo do contexto do Apura.

    Existe pra resolver um bug concreto: o chat perguntava "ano/cargo/UF/candidato"
    de novo mesmo com o escopo já salvo na Gestão, porque só a memória indexada
    (campanha_memoria) chegava ao prompt — não o escopo (ctl.campanha) nem o
    Radar (ctl.radar_config). Isso injeta os dois, com prioridade pro escopo.
    """
    status = status or {}
    radar_cfg = radar_cfg or {}
    nome = status.get("nm_urna") or status.get("nm_candidato") or radar_cfg.get("candidato_nome")
    uf = status.get("sg_uf") or radar_cfg.get("uf")
    cargo = status.get("cargo_label") or radar_cfg.get("cargo")
    ano = status.get("ano_ref")
    partido = status.get("sg_partido")
    sq = status.get("sq_candidato")
    if not (nome or uf or cargo):
        return ""
    linhas = [
        "ESCOPO DA CAMPANHA (já configurado nesta conta — NUNCA pergunte de novo "
        "ano/cargo/UF/candidato; use direto pra responder e pra filtrar tools):"
    ]
    if nome:
        linhas.append(
            f"- Candidato monitorado (o \"nosso\" desta campanha): {nome}"
            + (f" ({partido})" if partido else "")
        )
    if cargo:
        linhas.append(f"- Cargo: {cargo}")
    if uf:
        linhas.append(f"- UF: {uf}")
    if ano:
        linhas.append(f"- Ano de referência: {ano}")
    if sq:
        linhas.append(f"- sq_candidato (TSE): {sq}")
    linhas.append(
        "Perguntas do tipo \"quem é nosso candidato\", \"qual nosso cargo/UF/ano\" — "
        "responda direto com os dados acima, sem chamar tool e sem PENDENTE."
    )
    return "\n".join(linhas)


def salvar_estrategias(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    corpo: str,
    titulo: str = "Estratégias da campanha",
    rival: str | None = None,
    rivais: list[str] | None = None,
    fonte: str = "gestao",
) -> dict[str, Any]:
    """Substitui o bloco tipo=estrategias (um canônico por campanha)."""
    texto = (corpo or "").strip()
    if len(texto) < 20:
        raise ValueError("Texto de estratégias muito curto (mín. ~20 caracteres)")
    if len(texto) > 80_000:
        raise ValueError("Texto de estratégias grande demais (máx. ~80k)")
    limpar_tipos(conn, campanha_id, ["estrategias"])
    meta: dict[str, Any] = {}
    riv = (rival or "").strip()
    if riv:
        meta["rival"] = riv[:200]
    lista = [str(x).strip() for x in (rivais or []) if str(x).strip()]
    if lista:
        meta["rivais"] = lista[:12]
    elif riv:
        meta["rivais"] = [riv[:200]]
    bid = upsert_bloco(
        conn,
        campanha_id,
        tipo="estrategias",
        titulo=(titulo or "Estratégias da campanha")[:300],
        corpo=texto,
        fonte=fonte,
        nivel="indicio",
        meta=meta,
    )
    return {
        "ok": True,
        "id": bid,
        "tipo": "estrategias",
        "titulo": (titulo or "Estratégias da campanha")[:300],
        "rival": meta.get("rival"),
        "rivais": meta.get("rivais") or [],
        "chars": len(texto),
    }


def obter_estrategias(conn: psycopg.Connection, campanha_id: str) -> dict[str, Any] | None:
    itens = listar(conn, campanha_id, tipo="estrategias", limite=1)
    return itens[0] if itens else None


def consultar_para_apura(
    conn: psycopg.Connection,
    campanha_id: str,
    *,
    tipo: str | None = None,
    query: str | None = None,
    limite: int = 8,
) -> dict[str, Any]:
    """Consulta sob demanda para a tool do chat (não inventa cifra)."""
    lim = max(1, min(int(limite or 8), 20))
    tipo_n = (tipo or "").strip().lower() or None
    # aliases amigáveis
    aliases = {
        "estrategia": "estrategias",
        "estratégias": "estrategias",
        "pesquisa": "dossie_pesquisas",
        "pesquisas": "dossie_pesquisas",
        "dossiê": "dossie",
        "dossie": "dossie",
        "perfil": "perfil_eleitor",
        "rival": "base_concorrentes",
        "concorrentes": "base_concorrentes",
        "redes": "base_redes",
    }
    if tipo_n in aliases:
        tipo_n = aliases[tipo_n]
    # dossie = também variantes
    itens: list[dict[str, Any]] = []
    if tipo_n == "dossie":
        for b in listar(conn, campanha_id, query=query, limite=40):
            if (b.get("tipo") or "").startswith("dossie"):
                itens.append(b)
            if len(itens) >= lim:
                break
    else:
        itens = listar(conn, campanha_id, tipo=tipo_n, query=query, limite=lim)

    out_itens = []
    for b in itens[:lim]:
        corpo = b.get("corpo") or ""
        out_itens.append(
            {
                "tipo": b.get("tipo"),
                "titulo": b.get("titulo"),
                "resumo": corpo[:6000],
                "fonte": b.get("fonte"),
                "nivel": b.get("nivel"),
                "meta": b.get("meta") or {},
            }
        )
    return {
        "status": "ok" if out_itens else "vazio",
        "nivel": "indicio",
        "itens": out_itens,
        "mensagem": None
        if out_itens
        else "nenhum bloco neste filtro — grave estratégias/dossiê na Gestão ou rode o motor",
        "nota_metodologica": (
            "Memória de campanha (ctl.campanha_memoria). Indício/contexto — "
            "cifra oficial só via tools de urna."
        ),
    }


def texto_para_apura(conn: psycopg.Connection, campanha_id: str, *, max_chars: int = 12000) -> str:
    """Concatena blocos prioritários; reserva fatia para estrategias e pesquisas."""
    garantidos: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for tipo in ("estrategias", "dossie_pesquisas", "dossie", "perfil_eleitor"):
        for b in listar(conn, campanha_id, tipo=tipo, limite=3):
            bid = b.get("id") or ""
            if bid and bid in seen_ids:
                continue
            if bid:
                seen_ids.add(bid)
            garantidos.append(b)
    # demais dossie_*
    for b in listar(conn, campanha_id, limite=40):
        tipo = b.get("tipo") or ""
        if tipo.startswith("dossie") and tipo not in ("dossie", "dossie_pesquisas"):
            bid = b.get("id") or ""
            if bid and bid in seen_ids:
                continue
            if bid:
                seen_ids.add(bid)
            garantidos.append(b)
    resto = []
    for b in listar(conn, campanha_id, limite=40):
        bid = b.get("id") or ""
        if bid and bid in seen_ids:
            continue
        resto.append(b)

    blocos = garantidos + resto
    if not blocos:
        return ""
    partes: list[str] = [
        "CONHECIMENTO DA CAMPANHA (memória indexada — contextualiza; cifras oficiais vêm das tools):\n"
        "Prioridade fixa: estrategias → dossiê/pesquisas → perfil → demais bases. "
        "Cifra de urna só via tools."
    ]
    used = len(partes[0])
    # Reserva ~35% do budget para os garantidos (estratégias/pesquisas/dossiê)
    reserve_for_rest = int(max_chars * 0.55)
    for i, b in enumerate(blocos):
        chunk = (
            f"\n### [{b['tipo']}] {b['titulo']}\n{b['corpo']}\n"
            f"(fonte: {b['fonte'] or 'campanha'} | nível: {b['nivel']})"
        )
        # primeiros garantidos podem usar até max_chars - reserve; depois o resto
        limit = max_chars if i < len(garantidos) else max_chars
        if i >= len(garantidos) and used > reserve_for_rest and used + len(chunk) > max_chars:
            break
        if used + len(chunk) > limit:
            if i < len(garantidos):
                # corta corpo do garantido em vez de pular
                room = max(limit - used - 120, 400)
                corpo = (b.get("corpo") or "")[:room]
                chunk = (
                    f"\n### [{b['tipo']}] {b['titulo']}\n{corpo}\n"
                    f"(fonte: {b['fonte'] or 'campanha'} | nível: {b['nivel']} | truncado)"
                )
                if used + len(chunk) > limit:
                    break
            else:
                break
        partes.append(chunk)
        used += len(chunk)
    return "\n".join(partes)
