"""Baixa prestação de contas candidatos (TSE CDN) para data/raw."""
from __future__ import annotations

import hashlib
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, year_dir

RAW = ROOT / "data" / "raw"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas"
UA = "inteligencia-eleitoral-brasil/0.1"
ANOS = [2014, 2016, 2018, 2020, 2022, 2024, 2026]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def url_ano(ano: int) -> str:
    return f"{CDN}/prestacao_de_contas_eleitorais_candidatos_{ano}.zip"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".zip.part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=600) as resp, part.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    part.replace(dest)


def main() -> None:
    falhas: list[dict] = []
    for ano in ANOS:
        dest_dir = year_dir("br_cand_contas", ano)
        dest = dest_dir / "origem.zip"
        if dest.exists() and dest.stat().st_size > 10_000:
            print("JA TEM contas", ano)
            continue
        url = url_ano(ano)
        print("GET", url)
        try:
            download(url, dest)
        except Exception as e:
            falhas.append({"ano": ano, "url": url, "erro": str(e)})
            print("FALHA contas", ano, e)
            continue
        digest = sha256_file(dest)
        (dest_dir / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
        meta = {
            "id_base": "br_cand_contas",
            "ano": str(ano),
            "baixado_em": date.today().isoformat(),
            "url": url,
            "bytes": dest.stat().st_size,
            "sha256": digest,
            "orgao": "TSE",
            "status": "bruto",
        }
        (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OK contas", ano, round(dest.stat().st_size / 1e6, 1), "MB")
    if falhas:
        print("FALTAS", json.dumps(falhas, ensure_ascii=False))
    print("DOWNLOAD_CONTAS_FIM")


if __name__ == "__main__":
    main()
