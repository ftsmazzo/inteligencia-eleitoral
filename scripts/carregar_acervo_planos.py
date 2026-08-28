"""Promove planos 2026 (MD+PDF+manifesto) para data/raw e carrega no acervo.

Fonte típica: pasta mineracao/Planos (fora deste repo) ou --fonte.

Uso:
  python scripts/carregar_acervo_planos.py
  python scripts/carregar_acervo_planos.py --fonte "C:/.../mineracao/Planos" --so-promover
  python scripts/carregar_acervo_planos.py --so-seed   # gera mcp/seed sem DB
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import date
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, dsn, load_env

ID_BASE = "acervo_plano_governo"
TIPO = "plano_governo"
CARGO = "presidente"
FONTE_ORGAO_TPL = "TSE Dados Abertos — proposta de governo {ano}"
CHUNK_MAX = 2200
CHUNK_MIN = 60
DEFAULT_FONTE = Path(r"C:\Users\anjo_\OneDrive\Projetos-FabriaIA\mineracao\Planos")
SEED_DIR = ROOT / "mcp" / "seed"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, m.group(2)


def limpar_md(body: str) -> str:
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"\(p\.\s*\d+\)", "", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def chunk_markdown(body: str) -> list[tuple[str, str]]:
    """Retorna lista (secao, texto)."""
    body = limpar_md(body)
    if not body:
        return []
    partes = re.split(r"(?m)^(#{1,3}\s+.+)$", body)
    secoes: list[tuple[str, str]] = []
    secao = ""
    buf: list[str] = []
    for i, parte in enumerate(partes):
        if i == 0 and parte.strip():
            buf.append(parte.strip())
            continue
        if re.match(r"^#{1,3}\s+", parte or ""):
            if buf:
                texto = "\n\n".join(buf).strip()
                if len(texto) >= CHUNK_MIN:
                    secoes.append((secao, texto))
            secao = re.sub(r"^#{1,3}\s+", "", parte).strip()
            buf = []
        elif parte.strip():
            buf.append(parte.strip())
    if buf:
        texto = "\n\n".join(buf).strip()
        if len(texto) >= CHUNK_MIN:
            secoes.append((secao, texto))

    out: list[tuple[str, str]] = []
    for sec, texto in secoes:
        if len(texto) <= CHUNK_MAX:
            out.append((sec, texto))
            continue
        paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
        atual: list[str] = []
        tam = 0
        for p in paragrafos:
            if tam + len(p) + 2 > CHUNK_MAX and atual:
                out.append((sec, "\n\n".join(atual)))
                atual = [p]
                tam = len(p)
            else:
                atual.append(p)
                tam += len(p) + 2
        if atual:
            bloco = "\n\n".join(atual)
            if len(bloco) >= CHUNK_MIN:
                out.append((sec, bloco))
    return out


def promover(fonte: Path, stamp: str, ano: int) -> Path:
    dest = ROOT / "data" / "raw" / ID_BASE / f"ano={ano}" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    md_dest = dest / "MD"
    md_dest.mkdir(exist_ok=True)

    manifesto_src = fonte / "MD" / "manifesto.json"
    if not manifesto_src.exists():
        raise SystemExit(f"manifesto ausente: {manifesto_src}")

    shutil.copy2(manifesto_src, dest / "manifesto.json")
    digests: dict[str, str] = {}

    for pdf in sorted(fonte.glob("Plano de Governo - *.pdf")):
        target = dest / pdf.name
        if not target.exists() or target.stat().st_size != pdf.stat().st_size:
            shutil.copy2(pdf, target)
        digests[pdf.name] = sha256_file(target)

    leiame = fonte / "LEIAME - Planos de Governo.pdf"
    if leiame.exists():
        target = dest / leiame.name
        shutil.copy2(leiame, target)
        digests[leiame.name] = sha256_file(target)

    for md in sorted((fonte / "MD").glob("*.md")):
        target = md_dest / md.name
        shutil.copy2(md, target)
        digests[f"MD/{md.name}"] = sha256_file(target)

    (dest / "origem.sha256").write_text(
        "\n".join(f"{v}  {k}" for k, v in sorted(digests.items())) + "\n",
        encoding="utf-8",
    )
    meta = {
        "id_base": ID_BASE,
        "ano": ano,
        "copiado_em": stamp,
        "origem": str(fonte),
        "orgao": FONTE_ORGAO_TPL.format(ano=ano),
        "arquivos": len(digests),
        "nota": f"Planos de governo presidente {ano} (MD + PDF). Texto canônico = MD.",
        "status": "bruto_promovido",
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("promovido", dest, "arquivos", len(digests))
    return dest


def docs_from_raw(raw_dir: Path, ano: int) -> list[dict]:
    manifesto = json.loads((raw_dir / "manifesto.json").read_text(encoding="utf-8"))
    fonte_orgao = FONTE_ORGAO_TPL.format(ano=ano)
    docs: list[dict] = []
    for item in manifesto:
        md_rel = item["arquivo_md"].replace("\\", "/")
        md_path = raw_dir / md_rel
        if not md_path.exists():
            md_path = raw_dir / "MD" / Path(md_rel).name
        if not md_path.exists():
            print("SKIP md", md_rel)
            continue
        text = md_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        nome = fm.get("candidato") or item.get("candidato") or md_path.stem
        cand_id = fm.get("candidato_id") or item.get("candidato_id") or md_path.stem
        pdf_name = item.get("arquivo_pdf") or ""
        pdf_path = raw_dir / pdf_name if pdf_name else None
        digest = sha256_file(md_path)
        chunks = chunk_markdown(body)
        docs.append(
            {
                "tipo": TIPO,
                "titulo": f"Plano de governo {ano} — {nome}",
                "descricao": f"Proposta de governo (presidente) registrada junto ao TSE, ano {ano}.",
                "nivel": "referencia",
                "ano_eleicao": ano,
                "vigencia_inicio": f"{ano - 1}-01-01",
                "vigencia_fim": f"{ano + 1}-01-01",
                "escopo": "BR",
                "sg_uf": None,
                "sg_partido": None,
                "nm_candidato": nome,
                "cargo": CARGO,
                "tags": ["plano_governo", "presidente", str(ano), cand_id],
                "fonte_url": None,
                "fonte_orgao": fonte_orgao,
                "sha256": digest,
                "id_base_raw": ID_BASE,
                "meta": {
                    "candidato_id": cand_id,
                    "arquivo_md": md_rel,
                    "arquivo_pdf": pdf_name,
                    "paginas_pdf": item.get("paginas_pdf"),
                    "pdf_sha256": sha256_file(pdf_path) if pdf_path and pdf_path.exists() else None,
                },
                "chunks": [{"ord": i, "secao": sec, "texto": txt} for i, (sec, txt) in enumerate(chunks)],
            }
        )
        print("doc", nome, "chunks", len(chunks))
    return docs


def escrever_seed(docs: list[dict], ano: int) -> Path:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    seed_path = SEED_DIR / f"acervo_planos_{ano}.jsonl"
    with seed_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print("seed", seed_path, "docs", len(docs))
    return seed_path


def carregar_db(docs: list[dict]) -> None:
    load_env()
    url = dsn()
    with psycopg.connect(url) as conn:
        # garante schema (idempotente)
        patch = ROOT / "sql" / "patch_partido_linha.sql"
        acervo = ROOT / "sql" / "patch_acervo.sql"
        if patch.exists():
            conn.execute(patch.read_text(encoding="utf-8"))
        if acervo.exists():
            conn.execute(acervo.read_text(encoding="utf-8"))
        conn.commit()

        with conn.cursor() as cur:
            for doc in docs:
                dig = doc["sha256"]
                cur.execute(
                    "SELECT id FROM acervo.documento WHERE sha256 = %s AND tipo = %s",
                    (dig, TIPO),
                )
                row = cur.fetchone()
                if row:
                    doc_id = row[0]
                    cur.execute("DELETE FROM acervo.chunk WHERE documento_id = %s", (doc_id,))
                    cur.execute(
                        """
                        UPDATE acervo.documento SET
                          titulo=%s, descricao=%s, nivel=%s, ano_eleicao=%s,
                          vigencia_inicio=%s, vigencia_fim=%s, escopo=%s,
                          nm_candidato=%s, cargo=%s, tags=%s, fonte_orgao=%s,
                          id_base_raw=%s, meta=%s, ativo=true, atualizado_em=now()
                        WHERE id=%s
                        """,
                        (
                            doc["titulo"],
                            doc["descricao"],
                            doc["nivel"],
                            doc["ano_eleicao"],
                            doc["vigencia_inicio"],
                            doc["vigencia_fim"],
                            doc["escopo"],
                            doc["nm_candidato"],
                            doc["cargo"],
                            doc["tags"],
                            doc["fonte_orgao"],
                            doc["id_base_raw"],
                            json.dumps(doc["meta"], ensure_ascii=False),
                            doc_id,
                        ),
                    )
                else:
                    doc_id = uuid.uuid4()
                    cur.execute(
                        """
                        INSERT INTO acervo.documento (
                          id, tipo, titulo, descricao, nivel, ano_eleicao,
                          vigencia_inicio, vigencia_fim, escopo, sg_partido,
                          nm_candidato, cargo, tags, fonte_orgao, sha256,
                          id_base_raw, meta
                        ) VALUES (
                          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
                        )
                        """,
                        (
                            doc_id,
                            doc["tipo"],
                            doc["titulo"],
                            doc["descricao"],
                            doc["nivel"],
                            doc["ano_eleicao"],
                            doc["vigencia_inicio"],
                            doc["vigencia_fim"],
                            doc["escopo"],
                            doc["sg_partido"],
                            doc["nm_candidato"],
                            doc["cargo"],
                            doc["tags"],
                            doc["fonte_orgao"],
                            dig,
                            doc["id_base_raw"],
                            json.dumps(doc["meta"], ensure_ascii=False),
                        ),
                    )
                for ch in doc["chunks"]:
                    cur.execute(
                        """
                        INSERT INTO acervo.chunk (documento_id, ord, secao, texto, token_count)
                        VALUES (%s,%s,%s,%s,%s)
                        """,
                        (
                            doc_id,
                            ch["ord"],
                            ch["secao"],
                            ch["texto"],
                            max(1, len(ch["texto"]) // 4),
                        ),
                    )
        conn.commit()
    print("carga ok", len(docs), "documentos")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", type=Path, default=DEFAULT_FONTE)
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--stamp", default=date.today().isoformat())
    ap.add_argument("--so-promover", action="store_true")
    ap.add_argument("--so-seed", action="store_true")
    ap.add_argument("--raw", type=Path, default=None, help="Usa raw já promovido")
    args = ap.parse_args()

    raw = args.raw
    if raw is None:
        if not args.fonte.exists():
            raise SystemExit(f"fonte inexistente: {args.fonte}")
        raw = promover(args.fonte, args.stamp, args.ano)
    if args.so_promover:
        return

    docs = docs_from_raw(raw, args.ano)
    if not docs:
        raise SystemExit("nenhum documento")
    escrever_seed(docs, args.ano)
    if args.so_seed:
        return
    try:
        carregar_db(docs)
    except Exception as e:
        print("AVISO: DB indisponível localmente — seed gerado para bootstrap no mcp-api:", e)


if __name__ == "__main__":
    main()
