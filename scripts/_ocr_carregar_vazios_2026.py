"""OCR + carga direta dos PDFs 2026 sem texto extraível."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carregar_propostas_governo import (  # noqa: E402
    _cargo_escopo,
    _doc_from_pdf,
    _flush_db,
    _mapa_cargo,
    _sha_bytes,
)
from tse_util import year_dir  # noqa: E402

ANO = 2026
SKIP = [
    ("BA", "2026BA50002544692_01.pdf"),
    ("PE", "2026PE170002537227_01.pdf"),
    ("RJ", "2026RJ190002537524_01.pdf"),
    ("RO", "2026RO220002551251_01.pdf"),
    ("SC", "2026SC240002548628_01.pdf"),
]

TESS_CANDIDATES = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]


def setup_tesseract() -> None:
    import pytesseract

    for p in TESS_CANDIDATES:
        if p.exists():
            pytesseract.pytesseract.tesseract_cmd = str(p)
            break
    else:
        raise SystemExit("tesseract.exe não encontrado")
    local_tess = Path(__file__).resolve().parents[1] / "data" / "qa" / "tessdata"
    if (local_tess / "por.traineddata").exists():
        os.environ["TESSDATA_PREFIX"] = str(local_tess)


def ocr_to_text(data: bytes, max_pages: int | None = None) -> str:
    import fitz
    import pytesseract
    from PIL import Image

    doc = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    n = len(doc) if max_pages is None else min(len(doc), max_pages)
    lang = "por" if (Path(__file__).resolve().parents[1] / "data" / "qa" / "tessdata" / "por.traineddata").exists() else "eng"
    for i in range(n):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        txt = pytesseract.image_to_string(img, lang=lang)
        txt = (txt or "").strip()
        if txt:
            parts.append(f"<!-- page: {i + 1} -->\n{txt}")
        print(f"    page {i+1}/{n} chars={len(txt)}", flush=True)
    return "\n\n".join(parts)


def main() -> None:
    setup_tesseract()
    os.environ.setdefault("DATABASE_URL", "")
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL")

    # monkeypatch extract para usar OCR pré-computado
    from carregar_propostas_governo import _chunk_texto
    import carregar_propostas_governo as cpg

    batch: list[dict] = []
    total = [0]
    for uf, fname in SKIP:
        path = year_dir("acervo_plano_governo", ANO) / "pdfs" / uf / fname
        if not path.exists():
            print("MISSING", path, flush=True)
            continue
        raw = path.read_bytes()
        print("OCR", uf, fname, "bytes", len(raw), flush=True)
        # RJ 143 páginas — OCR completo; pode demorar
        texto = ocr_to_text(raw)
        if len(texto.strip()) < 80:
            print("SKIP ainda vazio", fname, flush=True)
            continue

        # força _extrair_pdf a devolver OCR
        def _fake_extract(_data: bytes, _texto: str = texto) -> str:
            return _texto

        cpg._extrair_pdf = _fake_extract  # type: ignore
        cargo, escopo, sg_uf = _cargo_escopo(ANO, uf)
        mapa = _mapa_cargo(ANO, cargo, sg_uf)
        doc = _doc_from_pdf(
            ano=ANO,
            uf_hint=uf,
            cargo=cargo,
            escopo=escopo,
            sg_uf=sg_uf,
            mapa=mapa,
            fname=fname,
            raw=raw,
        )
        if not doc:
            # se chunk falhou por sanitize, monta manual
            chunks = _chunk_texto(texto)
            if not chunks:
                print("SKIP chunks", fname, flush=True)
                continue
            digest = _sha_bytes(raw)
            doc = {
                "tipo": "plano_governo",
                "titulo": f"Plano de governo {ANO} — {mapa.get('') or fname} ({uf})",
                "descricao": f"Proposta OCR ({cargo}) TSE, ano {ANO}.",
                "nivel": "referencia",
                "ano_eleicao": ANO,
                "vigencia_inicio": f"{ANO - 1}-01-01",
                "vigencia_fim": f"{ANO + 1}-01-01",
                "escopo": escopo,
                "sg_uf": sg_uf,
                "sg_partido": None,
                "nm_candidato": fname,
                "cargo": cargo,
                "tags": ["plano_governo", cargo, str(ANO), "ocr", uf],
                "fonte_url": f"https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo/proposta_governo_{ANO}_{uf}.zip",
                "fonte_orgao": f"TSE Dados Abertos — proposta de governo {ANO} (OCR)",
                "sha256": digest + "-ocr",
                "id_base_raw": "acervo_plano_governo",
                "meta": {"arquivo_pdf": fname, "ocr": True, "uf_zip": uf},
                "chunks": [{"ord": i, "secao": s, "texto": t} for i, (s, t) in enumerate(chunks)],
            }
        else:
            doc["fonte_orgao"] = (doc.get("fonte_orgao") or "") + " (OCR)"
            doc["tags"] = list(doc.get("tags") or []) + ["ocr"]
            doc["meta"] = {**(doc.get("meta") or {}), "ocr": True}
            # sha distinto para não colidir com skip anterior
            doc["sha256"] = doc["sha256"] + "-ocr"
        batch.append(doc)
        print("DOC", doc["nm_candidato"], "chunks", len(doc["chunks"]), flush=True)
        if len(batch) >= 1:
            _flush_db(batch, ANO, uf, total)
    print("OCR_CARGA_FIM", total[0], flush=True)


if __name__ == "__main__":
    main()
