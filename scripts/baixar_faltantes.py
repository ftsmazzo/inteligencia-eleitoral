"""Baixa faltantes do ciclo eleitoral direto para data/raw. Sem carga no banco."""
from __future__ import annotations

import hashlib
import json
import ssl
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(r"C:\Users\anjo_\OneDrive\Projetos-FabriaIA\inteligencia-eleitoral")
RAW = ROOT / "data" / "raw"
STAMP = date.today().isoformat()
UA = "inteligencia-eleitoral-brasil/0.1 (reuso TSE dados abertos)"

# URL estável CDN TSE (mesmo pacote do portal dadosabertos)
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"

JOBS = [
    ("br_mun_votacao_nominal", "2016", f"{CDN}/votacao_candidato_munzona/votacao_candidato_munzona_2016.zip"),
    ("br_mun_votacao_nominal", "2020", f"{CDN}/votacao_candidato_munzona/votacao_candidato_munzona_2020.zip"),
    ("br_mun_detalhe_apuracao", "2014", f"{CDN}/detalhe_votacao_munzona/detalhe_votacao_munzona_2014.zip"),
    ("br_mun_detalhe_apuracao", "2016", f"{CDN}/detalhe_votacao_munzona/detalhe_votacao_munzona_2016.zip"),
    ("br_mun_detalhe_apuracao", "2020", f"{CDN}/detalhe_votacao_munzona/detalhe_votacao_munzona_2020.zip"),
    ("br_mun_detalhe_apuracao", "2024", f"{CDN}/detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip"),
    ("br_cand_nominata", "2014", f"{CDN}/consulta_cand/consulta_cand_2014.zip"),
    ("br_cand_nominata", "2016", f"{CDN}/consulta_cand/consulta_cand_2016.zip"),
    ("br_mun_eleitorado_perfil", "2016", f"{CDN}/perfil_eleitorado/perfil_eleitorado_2016.zip"),
    ("br_mun_eleitorado_perfil", "2020", f"{CDN}/perfil_eleitorado/perfil_eleitorado_2020.zip"),
    ("br_mun_eleitorado_perfil", "2024", f"{CDN}/perfil_eleitorado/perfil_eleitorado_2024.zip"),
    ("br_cand_coligacao", "2014", f"{CDN}/consulta_coligacao/consulta_coligacao_2014.zip"),
    ("br_cand_coligacao", "2016", f"{CDN}/consulta_coligacao/consulta_coligacao_2016.zip"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=120) as resp, part.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    part.replace(dest)


def main() -> None:
    falhas = []
    for id_base, ano, url in JOBS:
        dest_dir = RAW / id_base / f"ano={ano}"
        dest = dest_dir / "origem.zip"
        if dest.exists() and dest.stat().st_size > 1000:
            print("JA TEM", id_base, ano)
            continue
        print("GET", url)
        try:
            download(url, dest)
        except Exception as e:
            falhas.append({"id_base": id_base, "ano": ano, "url": url, "erro": str(e)})
            print("FALHA", id_base, ano, e)
            continue
        digest = sha256_file(dest)
        (dest_dir / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
        meta = {
            "id_base": id_base,
            "ano": ano,
            "baixado_em": STAMP,
            "url": url,
            "bytes": dest.stat().st_size,
            "sha256": digest,
            "status": "bruto_completo_pendente_ciclo",
        }
        (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OK", id_base, ano, dest.stat().st_size)
    out = RAW / "_auditoria_downloads.json"
    out.write_text(json.dumps(falhas, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FALHAS", len(falhas), "->", out)


if __name__ == "__main__":
    main()
