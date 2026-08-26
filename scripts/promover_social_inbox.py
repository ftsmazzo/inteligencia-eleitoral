"""Promove CadÚnico e Bolsa municipal do inbox/ para data/raw (cópia + zip + SHA)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "inbox"
RAW = ROOT / "data" / "raw"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def promote(id_base: str, inbox_dir: str, pattern: str, anomes: int, nota: str) -> None:
    src = INBOX / inbox_dir
    files = sorted(src.glob(pattern))
    if not files:
        raise SystemExit(f"sem arquivos {src}/{pattern}")
    dest_dir = RAW / id_base / f"anomes={anomes}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    zpath = dest_dir / "origem.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    digest = sha256(zpath)
    (dest_dir / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id_base": id_base,
        "anomes": str(anomes),
        "copiado_em": date.today().isoformat(),
        "origem_inbox": inbox_dir,
        "arquivos": len(files),
        "bytes": zpath.stat().st_size,
        "sha256": digest,
        "orgao": "MDS",
        "nota": nota,
        "status": "bruto",
    }
    (dest_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(id_base, anomes, "files", len(files), "MB", round(zpath.stat().st_size / 1e6, 2))


def main() -> None:
    promote(
        "br_mun_cadunico",
        "cadunico",
        "cadun_*.csv",
        202607,
        "Cadastro Único municipal; competência 2026-07; IBGE 6 dígitos no CSV",
    )
    promote(
        "br_mun_bolsa_familia",
        "bolsa_mun",
        "pbf_*.csv",
        202608,
        "Bolsa Família municipal; competência 2026-08; IBGE 6 dígitos no CSV",
    )
    print("PROMOCAO_SOCIAL_FIM")


if __name__ == "__main__":
    main()
