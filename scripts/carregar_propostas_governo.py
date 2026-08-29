"""Extrai propostas TSE (ZIP de PDFs) → seed acervo + carga no Postgres.

Espera data/raw/acervo_plano_governo/ano=YYYY/origem.zip (via baixar_propostas_governo.py).

Uso:
  python scripts/carregar_propostas_governo.py 2018 2022
  python scripts/carregar_propostas_governo.py --so-seed 2022
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carregar_acervo_planos import (  # noqa: E402
    CHUNK_MAX,
    CHUNK_MIN,
    SEED_DIR,
    carregar_db,
    escrever_seed,
)
from tse_util import ROOT, dsn, find_zip, load_env, year_dir  # noqa: E402

ID_BASE = "acervo_plano_governo"
TIPO = "plano_governo"
CARGO = "presidente"
FONTE = "TSE Dados Abertos — proposta de governo {ano}"

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _chunk_texto(body: str) -> list[tuple[str, str]]:
    body = re.sub(r"[ \t]+\n", "\n", body or "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) < CHUNK_MIN:
        return []
    # quebra por páginas marcadas ou parágrafos
    partes = re.split(r"\n{2,}", body)
    out: list[tuple[str, str]] = []
    atual: list[str] = []
    tam = 0
    secao = "Proposta"
    ord_sec = 0
    for p in partes:
        p = p.strip()
        if not p:
            continue
        if tam + len(p) + 2 > CHUNK_MAX and atual:
            bloco = "\n\n".join(atual)
            if len(bloco) >= CHUNK_MIN:
                out.append((f"{secao} · parte {ord_sec + 1}" if ord_sec else secao, bloco))
                ord_sec += 1
            atual = [p]
            tam = len(p)
        else:
            atual.append(p)
            tam += len(p) + 2
    if atual:
        bloco = "\n\n".join(atual)
        if len(bloco) >= CHUNK_MIN:
            out.append((f"{secao} · parte {ord_sec + 1}" if ord_sec else secao, bloco))
    return out


def _extrair_pdf(data: bytes) -> str:
    if PdfReader is None:
        raise SystemExit("Instale pypdf: pip install pypdf")
    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    paginas: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = txt.strip()
        if txt:
            paginas.append(f"<!-- page: {i + 1} -->\n{txt}")
    return "\n\n".join(paginas)


def _guess_sq(name: str) -> str | None:
    base = Path(name).stem
    # padrões comuns: proposta_123456789012.pdf, 280000614517.pdf, NR_CAND...
    m = re.search(r"(20\d{2})?(\d{8,14})", base.replace(" ", ""))
    if m:
        return m.group(2)
    digits = re.sub(r"\D", "", base)
    if len(digits) >= 8:
        return digits[-12:] if len(digits) > 12 else digits
    return None


def _nome_from_file(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"(?i)proposta[_\s-]*de[_\s-]*governo", "", stem)
    stem = re.sub(r"(?i)plano[_\s-]*de[_\s-]*governo", "", stem)
    stem = re.sub(r"[_-]+", " ", stem).strip(" .-_")
    return stem or Path(name).stem


def _mapa_presidente(ano: int) -> dict[str, str]:
    """sq_candidato → nm_urna / nm_candidato (se DB disponível)."""
    out: dict[str, str] = {}
    try:
        load_env()
        import psycopg

        with psycopg.connect(dsn(), connect_timeout=20) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT sq_candidato::text,
                       coalesce(nullif(nm_urna, ''), nm_candidato)
                FROM eleicao.candidatura
                WHERE ano = %s AND cd_cargo = 1
                """,
                (ano,),
            ).fetchall()
            for sq, nome in rows:
                if sq and nome:
                    out[str(sq)] = str(nome).strip()
    except Exception as e:
        print("AVISO: mapa nominata indisponível — uso nome do arquivo:", e)
    return out


def docs_from_zip(ano: int) -> list[dict]:
    d = year_dir(ID_BASE, ano)
    zpath = find_zip(d)
    if not zpath:
        raise SystemExit(f"ZIP ausente: {d}/origem.zip — rode baixar_propostas_governo.py {ano}")

    mapa = _mapa_presidente(ano)
    pdf_dir = d / "pdfs"
    pdf_dir.mkdir(exist_ok=True)
    docs: list[dict] = []

    with zipfile.ZipFile(zpath) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.endswith("/")]
        members.sort()
        print("zip", zpath.name, "pdfs", len(members))
        for member in members:
            raw = zf.read(member)
            if len(raw) < 500:
                continue
            fname = Path(member.replace("\\", "/")).name
            target = pdf_dir / fname
            if not target.exists() or target.stat().st_size != len(raw):
                target.write_bytes(raw)

            sq = _guess_sq(fname)
            nome = mapa.get(sq or "") or _nome_from_file(fname)
            # tenta casar por sufixo do sq no mapa
            if nome == _nome_from_file(fname) and sq and mapa:
                for k, v in mapa.items():
                    if k.endswith(sq) or sq.endswith(k[-8:]):
                        nome = v
                        sq = k
                        break

            try:
                texto = _extrair_pdf(raw)
            except Exception as e:
                print("SKIP pdf", fname, e)
                continue
            chunks = _chunk_texto(texto)
            if not chunks:
                print("SKIP vazio", fname)
                continue

            digest = _sha_bytes(raw)
            cand_id = _fold(nome).lower().replace(" ", "-")[:80]
            docs.append(
                {
                    "tipo": TIPO,
                    "titulo": f"Plano de governo {ano} — {nome}",
                    "descricao": f"Proposta de governo (presidente) TSE Dados Abertos, ano {ano}.",
                    "nivel": "referencia",
                    "ano_eleicao": ano,
                    "vigencia_inicio": f"{ano - 1}-01-01",
                    "vigencia_fim": f"{ano + 1}-01-01",
                    "escopo": "BR",
                    "sg_uf": None,
                    "sg_partido": None,
                    "nm_candidato": nome,
                    "cargo": CARGO,
                    "tags": ["plano_governo", "presidente", str(ano), cand_id]
                    + ([f"sq:{sq}"] if sq else []),
                    "fonte_url": f"https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/proposta_governo_{ano}_BR.zip",
                    "fonte_orgao": FONTE.format(ano=ano),
                    "sha256": digest,
                    "id_base_raw": ID_BASE,
                    "meta": {
                        "arquivo_pdf": fname,
                        "sq_candidato": sq,
                        "bytes_pdf": len(raw),
                        "paginas_texto": texto.count("<!-- page:"),
                    },
                    "chunks": [{"ord": i, "secao": sec, "texto": txt} for i, (sec, txt) in enumerate(chunks)],
                }
            )
            print("doc", nome, "chunks", len(chunks), "sq", sq or "-")
    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("anos", nargs="*", type=int, default=[2018, 2022])
    ap.add_argument("--so-seed", action="store_true")
    args = ap.parse_args()

    if PdfReader is None:
        raise SystemExit("Instale pypdf: pip install pypdf")

    all_docs: list[dict] = []
    for ano in args.anos:
        docs = docs_from_zip(ano)
        if not docs:
            print("AVISO: nenhum doc", ano)
            continue
        escrever_seed(docs, ano)
        all_docs.extend(docs)

    if args.so_seed or not all_docs:
        return
    try:
        carregar_db(all_docs)
    except Exception as e:
        print("AVISO: DB indisponível — seeds gerados para bootstrap no mcp-api:", e)


if __name__ == "__main__":
    main()
