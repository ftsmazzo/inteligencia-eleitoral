"""Promove inbox/dados-manuais → data/raw (cópia + SHA-256). Não altera inbox."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "inbox" / "dados-manuais"
RAW = ROOT / "data" / "raw"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        digest = sha256(dest)
        print("JA", dest.relative_to(ROOT), flush=True)
        return digest
    # hardlink se possível (evita dobrar ~16GB); senão copy
    if dest.exists():
        dest.unlink()
    try:
        os.link(src, dest)
        print("LINK", dest.relative_to(ROOT), flush=True)
    except OSError:
        shutil.copy2(src, dest)
        print("COPY", dest.relative_to(ROOT), round(dest.stat().st_size / 1e6, 1), "MB", flush=True)
    digest = sha256(dest)
    sha_path = dest.parent / (dest.name + ".sha256")
    sha_path.write_text(digest + "\n", encoding="utf-8")
    return digest


def _meta(dest_dir: Path, id_base: str, ano: str, src: Path, digest: str, nota: str) -> None:
    meta = {
        "id_base": id_base,
        "ano": ano,
        "copiado_em": date.today().isoformat(),
        "origem_inbox": str(src.relative_to(ROOT)).replace("\\", "/"),
        "bytes": (dest_dir / "origem.zip").stat().st_size if (dest_dir / "origem.zip").exists() else None,
        "sha256": digest,
        "orgao": "TSE",
        "nota": nota,
        "status": "bruto",
    }
    # bytes do arquivo real se origem.zip não for o nome
    zips = list(dest_dir.glob("*.zip"))
    if zips:
        meta["bytes"] = zips[0].stat().st_size
        meta["arquivo"] = zips[0].name
    (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if not INBOX.exists():
        raise SystemExit(f"ausente: {INBOX}")

    for src in sorted(INBOX.glob("*.zip")):
        name = src.name
        # normaliza BR (1).zip
        name_norm = re.sub(r"\s*\(\d+\)", "", name)

        m_comp = re.match(r"consulta_cand_complementar_(\d{4})\.zip$", name_norm)
        m_rede = re.match(r"rede_social_candidato_(\d{4})\.zip$", name_norm)
        m_prop = re.match(r"proposta_governo_(\d{4})_([A-Z]{2})\.zip$", name_norm)

        if m_comp:
            ano = m_comp.group(1)
            dest_dir = RAW / "br_cand_complementar" / f"ano={ano}"
            dest = dest_dir / "origem.zip"
            digest = _copy(src, dest)
            _meta(dest_dir, "br_cand_complementar", ano, src, digest, "Informações complementares TSE")
            continue

        if m_rede:
            ano = m_rede.group(1)
            dest_dir = RAW / "br_cand_rede_social" / f"ano={ano}"
            dest = dest_dir / "origem.zip"
            digest = _copy(src, dest)
            _meta(dest_dir, "br_cand_rede_social", ano, src, digest, "Redes sociais candidatos TSE")
            continue

        if m_prop:
            ano, uf = m_prop.group(1), m_prop.group(2)
            dest_dir = RAW / "acervo_plano_governo" / f"ano={ano}"
            dest = dest_dir / f"proposta_governo_{ano}_{uf}.zip"
            digest = _copy(src, dest)
            # BR vira também origem.zip para script legado
            if uf == "BR":
                origem = dest_dir / "origem.zip"
                if not origem.exists() or origem.stat().st_size != dest.stat().st_size:
                    if origem.exists():
                        origem.unlink()
                    try:
                        os.link(dest, origem)
                    except OSError:
                        shutil.copy2(dest, origem)
            _meta(
                dest_dir,
                "acervo_plano_governo",
                ano,
                src,
                digest,
                f"Proposta de governo TSE UF={uf}",
            )
            continue

        print("SKIP nome não reconhecido:", name, flush=True)

    print("PROMOCAO_DADOS_MANUAIS_FIM", flush=True)


if __name__ == "__main__":
    main()
