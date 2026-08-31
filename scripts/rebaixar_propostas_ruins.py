"""Rebaixa ZIPs de proposta_governo corrompidos (truncados)."""
from __future__ import annotations

import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import year_dir

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo"
UA = "inteligencia-eleitoral-brasil/0.1 (reuso TSE dados abertos)"
ID_BASE = "acervo_plano_governo"


def _request(url: str, timeout: int = 900):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Referer": "https://dadosabertos.tse.jus.br/",
        },
    )
    return urllib.request.urlopen(req, context=ctx, timeout=timeout)


def zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            zf.namelist()
        return True
    except Exception:
        return False


def download(url: str, dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    with _request(url) as resp, part.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    if not zip_ok(part):
        part.unlink(missing_ok=True)
        raise RuntimeError(f"download inválido: {url}")
    part.replace(dest)


def main() -> None:
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    ufs = [u.upper() for u in sys.argv[2:]]
    d = year_dir(ID_BASE, ano)
    if not ufs:
        for z in sorted(d.glob(f"proposta_governo_{ano}_*.zip")):
            if not zip_ok(z):
                ufs.append(z.stem.split("_")[-1])
    print("rebaixar", ano, ufs, flush=True)
    for uf in ufs:
        dest = d / f"proposta_governo_{ano}_{uf}.zip"
        url = f"{CDN}/proposta_governo_{ano}_{uf}.zip"
        print("GET", url, flush=True)
        try:
            download(url, dest)
            print("OK", dest.name, dest.stat().st_size, flush=True)
        except Exception as e:
            print("FALHA", uf, e, flush=True)
    print("REBAIXA_FIM", flush=True)


if __name__ == "__main__":
    main()
