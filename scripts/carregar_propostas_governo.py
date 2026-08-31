"""Extrai propostas TSE (ZIP de PDFs) → staging → Postgres.

Espera data/raw/acervo_plano_governo/ano=YYYY/proposta_governo_YYYY_UF.zip

Uso:
  python scripts/carregar_propostas_governo.py 2018 2022
  python scripts/carregar_propostas_governo.py --uf SC,SP 2020
  python scripts/carregar_propostas_governo.py --so-db --uf SC 2020   # só staging→DB
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
    _sanitize_doc,
    carregar_db,
    escrever_seed,
)
from tse_util import ROOT, dsn, find_zip, load_env, year_dir  # noqa: E402

ID_BASE = "acervo_plano_governo"
TIPO = "plano_governo"
FONTE = "TSE Dados Abertos — proposta de governo {ano}"
STAGING = ROOT / "data" / "staging" / ID_BASE
DB_BATCH = 20

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def _sanitize_unicode(s: str) -> str:
    if not s:
        return s or ""
    return "".join(
        ch if not (0xD800 <= ord(ch) <= 0xDFFF) else "\ufffd" for ch in s
    )


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _chunk_texto(body: str) -> list[tuple[str, str]]:
    body = _sanitize_unicode(body)
    body = re.sub(r"[ \t]+\n", "\n", body or "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) < CHUNK_MIN:
        return []
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
        txt = _sanitize_unicode(txt).strip()
        if txt:
            paginas.append(f"<!-- page: {i + 1} -->\n{txt}")
    return _sanitize_unicode("\n\n".join(paginas))


def _guess_sq(name: str) -> str | None:
    base = Path(name).stem
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


def _cargo_escopo(ano: int, uf: str | None) -> tuple[str, str, str | None]:
    if uf in (None, "BR"):
        return "presidente", "BR", None
    if ano in (2014, 2018, 2022, 2026):
        return "governador", "UF", uf
    return "prefeito", "UF", uf


def _mapa_cargo(ano: int, cargo: str, uf: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    cd = {"presidente": 1, "governador": 3, "prefeito": 11}.get(cargo)
    if cd is None:
        return out
    try:
        load_env()
        import psycopg

        with psycopg.connect(dsn(), connect_timeout=20) as conn:
            sql = """
                SELECT DISTINCT sq_candidato::text,
                       coalesce(nullif(nm_urna, ''), nm_candidato)
                FROM eleicao.candidatura
                WHERE ano = %s AND cd_cargo = %s
            """
            args: list = [ano, cd]
            if uf:
                sql += " AND sg_uf = %s"
                args.append(uf)
            rows = conn.execute(sql, args).fetchall()
            for sq, nome in rows:
                if sq and nome:
                    out[str(sq)] = str(nome).strip()
    except Exception as e:
        print("AVISO: mapa nominata indisponível — uso nome do arquivo:", e, flush=True)
    return out


def _staging_path(ano: int, uf: str | None) -> Path:
    d = STAGING / f"ano={ano}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"docs_{uf or 'BR'}.jsonl"


def _load_staging(path: Path) -> list[dict]:
    if not path.exists():
        return []
    docs: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return docs


def _append_staging(path: Path, doc: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_sanitize_doc(doc), ensure_ascii=False) + "\n")


def _flush_db(batch: list[dict], ano: int, uf: str | None, total_ok: list[int]) -> None:
    if not batch:
        return
    carregar_db(batch)
    total_ok[0] += len(batch)
    print("DB_OK_BATCH", ano, uf or "BR", len(batch), "acum", total_ok[0], flush=True)
    batch.clear()


def _doc_from_pdf(
    *,
    ano: int,
    uf_hint: str | None,
    cargo: str,
    escopo: str,
    sg_uf: str | None,
    mapa: dict[str, str],
    fname: str,
    raw: bytes,
) -> dict | None:
    if len(raw) < 500:
        return None
    if re.search(r"(?i)^leiame", Path(fname).stem):
        print("SKIP leiame", fname, flush=True)
        return None
    sq = _guess_sq(fname)
    nome = mapa.get(sq or "") or _nome_from_file(fname)
    if nome == _nome_from_file(fname) and sq and mapa:
        for k, v in mapa.items():
            if k.endswith(sq) or sq.endswith(k[-8:]):
                nome = v
                sq = k
                break
    try:
        texto = _extrair_pdf(raw)
    except Exception as e:
        print("SKIP pdf", fname, e, flush=True)
        return None
    texto = texto.replace("\x00", "")
    chunks = _chunk_texto(texto)
    if not chunks:
        print("SKIP vazio", fname, flush=True)
        return None
    digest = _sha_bytes(raw)
    cand_id = _fold(nome).lower().replace(" ", "-")[:80]
    return {
        "tipo": TIPO,
        "titulo": f"Plano de governo {ano} — {nome}"
        + (f" ({sg_uf})" if sg_uf else ""),
        "descricao": f"Proposta de governo ({cargo}) TSE Dados Abertos, ano {ano}.",
        "nivel": "referencia",
        "ano_eleicao": ano,
        "vigencia_inicio": f"{ano - 1}-01-01",
        "vigencia_fim": f"{ano + 1}-01-01",
        "escopo": escopo,
        "sg_uf": sg_uf,
        "sg_partido": None,
        "nm_candidato": nome,
        "cargo": cargo,
        "tags": ["plano_governo", cargo, str(ano), cand_id]
        + ([sg_uf] if sg_uf else [])
        + ([f"sq:{sq}"] if sq else []),
        "fonte_url": (
            f"https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/"
            f"proposta_governo_{ano}_{uf_hint or 'BR'}.zip"
        ),
        "fonte_orgao": FONTE.format(ano=ano),
        "sha256": digest,
        "id_base_raw": ID_BASE,
        "meta": {
            "arquivo_pdf": fname,
            "sq_candidato": sq,
            "bytes_pdf": len(raw),
            "paginas_texto": texto.count("<!-- page:"),
            "uf_zip": uf_hint or "BR",
        },
        "chunks": [{"ord": i, "secao": sec, "texto": txt} for i, (sec, txt) in enumerate(chunks)],
    }


def process_one_zip(
    ano: int,
    zpath: Path,
    uf_hint: str | None,
    *,
    so_seed: bool = False,
    so_db: bool = False,
) -> tuple[list[dict], int]:
    """Extrai (com checkpoint) e/ou carrega DB em lotes. Retorna (docs, n_db)."""
    cargo, escopo, sg_uf = _cargo_escopo(ano, uf_hint)
    stag = _staging_path(ano, uf_hint)
    existing = _load_staging(stag)
    by_sha = {d["sha256"]: d for d in existing if d.get("sha256")}
    print(
        "staging",
        stag.name,
        "ja",
        len(by_sha),
        "zip",
        zpath.name,
        flush=True,
    )

    total_ok = [0]
    batch: list[dict] = []

    if so_db:
        docs = list(by_sha.values())
        print("so-db", ano, uf_hint or "BR", "docs", len(docs), flush=True)
        for i in range(0, len(docs), DB_BATCH):
            _flush_db(docs[i : i + DB_BATCH], ano, uf_hint, total_ok)
        print("DB_OK", ano, uf_hint or "BR", total_ok[0], flush=True)
        return docs, total_ok[0]

    mapa = _mapa_cargo(ano, cargo, sg_uf)
    pdf_dir = year_dir(ID_BASE, ano) / "pdfs" / (uf_hint or "BR")
    pdf_dir.mkdir(parents=True, exist_ok=True)

    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile as e:
        print("AVISO ZIP_RUIM", zpath.name, e, flush=True)
        # ainda tenta carregar o que já estiver no staging
        docs = list(by_sha.values())
        if docs and not so_seed:
            for i in range(0, len(docs), DB_BATCH):
                try:
                    _flush_db(docs[i : i + DB_BATCH], ano, uf_hint, total_ok)
                except Exception as ex:
                    print("AVISO DB", ano, uf_hint, ex, flush=True)
            if total_ok[0]:
                print("DB_OK", ano, uf_hint or "BR", total_ok[0], flush=True)
        return docs, total_ok[0]

    with zf:
        members = [
            n for n in zf.namelist() if n.lower().endswith(".pdf") and not n.endswith("/")
        ]
        members.sort()
        print(
            "zip",
            zpath.name,
            "uf",
            uf_hint or "BR",
            "cargo",
            cargo,
            "pdfs",
            len(members),
            flush=True,
        )
        for member in members:
            fname = Path(member.replace("\\", "/")).name
            target = pdf_dir / fname
            # reusa bytes já gravados no disco (retomada sem ler ZIP de novo)
            if target.exists() and target.stat().st_size >= 500:
                raw = target.read_bytes()
            else:
                raw = zf.read(member)
                if len(raw) >= 500:
                    target.write_bytes(raw)

            digest = _sha_bytes(raw) if len(raw) >= 500 else ""
            if digest and digest in by_sha:
                continue

            doc = _doc_from_pdf(
                ano=ano,
                uf_hint=uf_hint,
                cargo=cargo,
                escopo=escopo,
                sg_uf=sg_uf,
                mapa=mapa,
                fname=fname,
                raw=raw,
            )
            if not doc:
                continue
            by_sha[doc["sha256"]] = doc
            _append_staging(stag, doc)
            print(
                "doc",
                doc["nm_candidato"],
                "chunks",
                len(doc["chunks"]),
                "sq",
                (doc.get("meta") or {}).get("sq_candidato") or "-",
                flush=True,
            )
            if not so_seed:
                batch.append(doc)
                if len(batch) >= DB_BATCH:
                    try:
                        _flush_db(batch, ano, uf_hint, total_ok)
                    except Exception as e:
                        print("AVISO DB", ano, uf_hint, e, flush=True)
                        batch.clear()

    if not so_seed and batch:
        try:
            _flush_db(batch, ano, uf_hint, total_ok)
        except Exception as e:
            print("AVISO DB", ano, uf_hint, e, flush=True)

    docs = list(by_sha.values())
    if not so_seed and total_ok[0]:
        print("DB_OK", ano, uf_hint or "BR", total_ok[0], flush=True)
    elif so_seed:
        print("SEED_ONLY", ano, uf_hint or "BR", len(docs), flush=True)
    return docs, total_ok[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("anos", nargs="*", type=int, default=[2018, 2022])
    ap.add_argument("--so-seed", action="store_true")
    ap.add_argument("--so-db", action="store_true", help="Só carrega staging→DB (sem PDF)")
    ap.add_argument("--so-br", action="store_true", help="Só pacotes BR (presidente)")
    ap.add_argument(
        "--uf",
        action="append",
        default=[],
        help="Filtrar UF (repetir ou CSV). Com --uf não reescreve seed do ano.",
    )
    args = ap.parse_args()
    ufs_filtro = {u.strip().upper() for raw in args.uf for u in raw.split(",") if u.strip()}

    if PdfReader is None and not args.so_db:
        raise SystemExit("Instale pypdf: pip install pypdf")

    total_docs = 0
    for ano in args.anos:
        d = year_dir(ID_BASE, ano)
        named = sorted(d.glob("proposta_governo_*.zip")) if d.exists() else []
        if args.so_br:
            named = [p for p in named if p.name.upper().endswith("_BR.ZIP")]
        if ufs_filtro:
            named = [
                p
                for p in named
                if (m := re.search(r"_([A-Z]{2})\.zip$", p.name, re.I))
                and m.group(1).upper() in ufs_filtro
            ]
        if not named:
            z = find_zip(d) if d.exists() else None
            named = [z] if z else []
        if not named:
            # so-db pode usar só staging
            if args.so_db and ufs_filtro:
                for uf in sorted(ufs_filtro):
                    fake = d / f"proposta_governo_{ano}_{uf}.zip"
                    docs, n = process_one_zip(
                        ano, fake, uf, so_seed=args.so_seed, so_db=True
                    )
                    total_docs += n
                continue
            print("AVISO: nenhum zip", ano, flush=True)
            continue

        year_docs: list[dict] = []
        for zpath in named:
            m = re.search(r"proposta_governo_(\d{4})_([A-Z]{2})\.zip$", zpath.name, re.I)
            uf_hint = (
                m.group(2).upper()
                if m
                else ("BR" if "origem" in zpath.name.lower() else None)
            )
            docs, n = process_one_zip(
                ano,
                zpath,
                uf_hint,
                so_seed=args.so_seed,
                so_db=args.so_db,
            )
            year_docs.extend(docs)
            total_docs += n

        if year_docs and not ufs_filtro and not args.so_db:
            try:
                escrever_seed(year_docs, ano)
            except Exception as e:
                print("AVISO seed", ano, e, flush=True)

    print("CARGA_PROPOSTAS_FIM docs", total_docs, flush=True)


if __name__ == "__main__":
    main()
