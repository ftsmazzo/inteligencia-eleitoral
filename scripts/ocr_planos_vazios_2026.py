"""OCR PDFs de plano 2026 sem texto (pymupdf render + tesseract se houver).

Uso:
  python scripts/ocr_planos_vazios_2026.py
  python scripts/ocr_planos_vazios_2026.py --uf RJ,AP
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carregar_propostas_governo import process_one_zip  # noqa: E402
from tse_util import ROOT, year_dir  # noqa: E402

ANO = 2026
ID_BASE = "acervo_plano_governo"
SKIP_KNOWN = [
    "2026BA50002544692_01.pdf",
    "2026PE170002537227_01.pdf",
    "2026RJ190002537524_01.pdf",
    "2026RO220002551251_01.pdf",
    "2026SC240002548628_01.pdf",
]


def _has_text(data: bytes, min_chars: int = 80) -> bool:
    try:
        from pypdf import PdfReader

        r = PdfReader(BytesIO(data))
        txt = "".join((p.extract_text() or "") for p in r.pages)
        return len(txt.strip()) >= min_chars
    except Exception:
        return False


def ocr_pdf(data: bytes) -> bytes | None:
    """Retorna PDF com camada de texto, ou None se OCR indisponível."""
    try:
        import fitz  # pymupdf
    except ImportError:
        print("AVISO: pymupdf ausente", flush=True)
        return None

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        # tenta só extrair com fitz (às vezes melhor que pypdf)
        doc = fitz.open(stream=data, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text("text") or "")
        joined = "\n".join(parts).strip()
        if len(joined) >= 80:
            # já tem texto via fitz — regrava como PDF "texto" simples não necessário;
            # caller pode usar extract direto. Sinaliza com None + side channel.
            return b"__FITZ_TEXT__:" + joined.encode("utf-8", errors="replace")
        print("AVISO: pytesseract/Pillow ausentes — sem OCR de imagem", flush=True)
        return None

    src = fitz.open(stream=data, filetype="pdf")
    out = fitz.open()
    for i, page in enumerate(src):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang="por+eng")
        # página nova com texto
        np = out.new_page(width=page.rect.width, height=page.rect.height)
        # insere imagem + texto invisível aproximado
        np.insert_image(page.rect, pixmap=pix)
        if text.strip():
            np.insert_text((36, 36), text[:5000], fontsize=1, render_mode=3)
        print(f"  ocr page {i+1}/{len(src)} chars={len(text.strip())}", flush=True)
    buf = BytesIO()
    out.save(buf)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="", help="CSV de UFs; vazio = todas com pdfs conhecidos")
    ap.add_argument("--so-list", action="store_true")
    args = ap.parse_args()
    ufs = {u.strip().upper() for u in args.uf.split(",") if u.strip()}

    pdf_root = year_dir(ID_BASE, ANO) / "pdfs"
    targets: list[tuple[str, Path]] = []
    for pdf in SKIP_KNOWN:
        m = re.match(r"2026([A-Z]{2})", pdf)
        if not m:
            continue
        uf = m.group(1)
        if ufs and uf not in ufs:
            continue
        p = pdf_root / uf / pdf
        if not p.exists():
            # extrai do zip se precisar
            z = year_dir(ID_BASE, ANO) / f"proposta_governo_{ANO}_{uf}.zip"
            if z.exists():
                with zipfile.ZipFile(z) as zf:
                    for n in zf.namelist():
                        if Path(n).name == pdf:
                            p.parent.mkdir(parents=True, exist_ok=True)
                            p.write_bytes(zf.read(n))
                            break
        if p.exists():
            targets.append((uf, p))

    print("alvos", len(targets), flush=True)
    if args.so_list:
        for uf, p in targets:
            print(uf, p.name, p.stat().st_size, "texto" if _has_text(p.read_bytes()) else "vazio")
        return

    touched_ufs: set[str] = set()
    for uf, p in targets:
        raw = p.read_bytes()
        if _has_text(raw):
            print("JA_TEXTO", p.name, flush=True)
            continue
        print("OCR", uf, p.name, flush=True)
        out = ocr_pdf(raw)
        if out is None:
            print("FALHA_OCR", p.name, flush=True)
            continue
        if out.startswith(b"__FITZ_TEXT__:"):
            # salva sidecar .txt para carga manual futura
            p.with_suffix(".ocr.txt").write_bytes(out.split(b":", 1)[1])
            print("FITZ_TXT", p.with_suffix(".ocr.txt").name, flush=True)
            continue
        bak = p.with_suffix(".pdf.pre_ocr")
        if not bak.exists():
            bak.write_bytes(raw)
        p.write_bytes(out)
        touched_ufs.add(uf)
        print("OK_OCR", p.name, len(out), flush=True)

    # reprocessa zips das UFs tocadas (ou força lista)
    for uf in sorted(touched_ufs | (ufs or set())):
        z = year_dir(ID_BASE, ANO) / f"proposta_governo_{ANO}_{uf}.zip"
        if not z.exists():
            continue
        # se OCR gravou PDF no disco, process_one_zip reusa target.exists()
        print("RECARGA", uf, flush=True)
        process_one_zip(ANO, z, uf)


if __name__ == "__main__":
    main()
