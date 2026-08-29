"""Baixa propostas de governo (TSE) — ZIP BR por ano — para data/raw.

Padrão igual a baixar_contas: CDN + fallback CKAN.

Uso:
  python scripts/baixar_propostas_governo.py
  python scripts/baixar_propostas_governo.py 2018 2022
"""
from __future__ import annotations

import hashlib
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import year_dir

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/proposta_governo"
UA = "inteligencia-eleitoral-brasil/0.1 (reuso TSE dados abertos; +fredmazzo@gmail.com)"
ID_BASE = "acervo_plano_governo"
ANOS = [2018, 2022]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def url_cdn(ano: int) -> list[str]:
    return [
        f"{CDN}/proposta_governo_{ano}_BR.zip",
        f"{CDN}/proposta_governo_{ano}.zip",
    ]


def _request(url: str, timeout: int = 600):
    ctx = ssl.create_default_context()
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": "https://dadosabertos.tse.jus.br/",
        "Origin": "https://dadosabertos.tse.jus.br",
    }
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, context=ctx, timeout=timeout)


def urls_ckan(ano: int) -> list[str]:
    out: list[str] = []
    for pid in (f"candidatos-{ano}", f"dadosabertos-tse-jus-br-dataset-candidatos-{ano}"):
        api = f"https://dadosabertos.tse.jus.br/api/3/action/package_show?id={pid}"
        try:
            with _request(api, timeout=120) as resp:
                pkg = json.loads(resp.read()).get("result") or {}
        except Exception:
            continue
        for res in pkg.get("resources") or []:
            name = f"{res.get('name', '')} {res.get('description', '')}"
            u = (res.get("url") or "").strip()
            if not u:
                continue
            low = name.lower()
            if "proposta" not in low and "governo" not in low:
                continue
            if "br" not in low and "_br" not in u.lower():
                continue
            if u not in out:
                out.append(u)
    return out


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    with _request(url) as resp, part.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    part.replace(dest)


def main() -> None:
    anos = [int(a) for a in sys.argv[1:]] or ANOS
    falhas: list[dict] = []
    for ano in anos:
        dest_dir = year_dir(ID_BASE, ano)
        dest = dest_dir / "origem.zip"
        if dest.exists() and dest.stat().st_size > 10_000:
            print("JA TEM propostas", ano, round(dest.stat().st_size / 1e6, 1), "MB")
            continue
        candidatos = url_cdn(ano)
        try:
            for u in urls_ckan(ano):
                if u not in candidatos:
                    candidatos.append(u)
        except Exception as e:
            print("CKAN skip", ano, e)
        ok = False
        last_err = ""
        used = ""
        for url in candidatos:
            print("GET", url)
            try:
                download(url, dest)
                ok = True
                used = url
                break
            except Exception as e:
                last_err = str(e)
                print("FALHA", ano, e)
        if not ok:
            falhas.append({"ano": ano, "erro": last_err})
            continue
        digest = sha256_file(dest)
        (dest_dir / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
        meta = {
            "id_base": ID_BASE,
            "ano": str(ano),
            "baixado_em": date.today().isoformat(),
            "url": used,
            "bytes": dest.stat().st_size,
            "sha256": digest,
            "orgao": "TSE Dados Abertos — proposta de governo",
            "status": "bruto",
            "escopo": "BR",
            "cargo": "presidente",
        }
        (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OK propostas", ano, round(dest.stat().st_size / 1e6, 1), "MB")
    if falhas:
        print("FALTAS", json.dumps(falhas, ensure_ascii=False))
    print("DOWNLOAD_PROPOSTAS_FIM")


if __name__ == "__main__":
    main()
