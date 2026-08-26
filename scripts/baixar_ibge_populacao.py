"""Baixa população municipal IBGE (SIDRA) para data/raw."""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT

RAW = ROOT / "data" / "raw"
UA = "inteligencia-eleitoral-brasil/0.1"

# Estimativas: tabela 6579 (sem anos de censo 2010/2022/2023).
ESTIMATIVA_ANOS = [2014, 2016, 2018, 2020, 2021, 2024, 2025]
# Censos: total residentes.
CENSO = {
    2010: "https://apisidra.ibge.gov.br/values/t/1378/n6/all/v/93/p/2010/f/c/h/y",
    2022: "https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022/f/c/h/y",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def save_raw(id_base: str, ano: int, url: str, payload: bytes, nota: str) -> Path:
    d = RAW / id_base / f"ano={ano}"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "origem.json"
    dest.write_bytes(payload)
    digest = sha256(dest)
    (d / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id_base": id_base,
        "ano": str(ano),
        "copiado_em": date.today().isoformat(),
        "url": url,
        "orgao": "IBGE/SIDRA",
        "bytes": dest.stat().st_size,
        "sha256": digest,
        "nota": nota,
        "status": "bruto",
    }
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    data = json.loads(payload)
    print(id_base, ano, "rows", max(len(data) - 1, 0), "MB", round(len(payload) / 1e6, 2))
    return dest


def main() -> None:
    for ano in ESTIMATIVA_ANOS:
        url = (
            f"https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/all/p/{ano}/f/c/h/y"
        )
        save_raw(
            "br_mun_estimativas",
            ano,
            url,
            fetch(url),
            "População residente estimada (SIDRA 6579), 1º julho",
        )
    for ano, url in CENSO.items():
        save_raw(
            "br_mun_censo",
            ano,
            url,
            fetch(url),
            f"Censo Demográfico {ano} população residente (SIDRA)",
        )
    print("DOWNLOAD_IBGE_POP_FIM")


if __name__ == "__main__":
    main()
