"""Baixa dumps oficiais Câmara + Senado para data/raw (módulo parlamentar)."""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT

RAW = ROOT / "data" / "raw"
UA = "inteligencia-eleitoral-brasil/0.1"
ANOS = [2023, 2024, 2025, 2026]
CAMARA = "https://dadosabertos.camara.leg.br/arquivos"
FALTAS: list[dict] = []


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def save(id_base: str, slot: str, url: str, payload: bytes, nome: str, nota: str) -> Path:
    d = RAW / id_base / slot
    d.mkdir(parents=True, exist_ok=True)
    dest = d / nome
    dest.write_bytes(payload)
    digest = sha256_bytes(payload)
    (d / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id_base": id_base,
        "slot": slot,
        "url": url,
        "arquivo": nome,
        "copiado_em": date.today().isoformat(),
        "orgao": "Camara" if "camara.leg.br" in url else "Senado",
        "bytes": len(payload),
        "sha256": digest,
        "nota": nota,
        "status": "bruto",
    }
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OK", id_base, slot, nome, round(len(payload) / 1e6, 2), "MB", flush=True)
    return dest


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def try_fetch(id_base: str, slot: str, url: str, nome: str, nota: str) -> bool:
    dest_dir = RAW / id_base / slot
    dest = dest_dir / nome
    if dest.exists() and dest.stat().st_size > 0:
        print("SKIP", id_base, slot, nome, flush=True)
        return True
    try:
        payload = fetch(url)
        if len(payload) < 50:
            raise RuntimeError("payload muito pequeno")
        save(id_base, slot, url, payload, nome, nota)
        return True
    except Exception as e:
        FALTAS.append(
            {
                "id_base": id_base,
                "slot": slot,
                "url": url,
                "arquivo": nome,
                "erro": f"{type(e).__name__}: {e}",
            }
        )
        print("FALTA", id_base, slot, url, e, flush=True)
        return False


def main() -> None:
    # Estáticos Câmara
    try_fetch(
        "br_camara_legislaturas",
        "estatica",
        f"{CAMARA}/legislaturas/json/legislaturas.json",
        "origem.json",
        "Todas as legislaturas",
    )
    try_fetch(
        "br_camara_deputados",
        "estatica",
        f"{CAMARA}/deputados/json/deputados.json",
        "origem.json",
        "Cadastro histórico de deputados",
    )

    series = [
        ("br_camara_proposicoes", "proposicoes", "proposicoes-{ano}.csv"),
        ("br_camara_proposicoes_autores", "proposicoesAutores", "proposicoesAutores-{ano}.csv"),
        ("br_camara_proposicoes_temas", "proposicoesTemas", "proposicoesTemas-{ano}.csv"),
        ("br_camara_votacoes", "votacoes", "votacoes-{ano}.csv"),
        ("br_camara_votacoes_votos", "votacoesVotos", "votacoesVotos-{ano}.csv"),
        ("br_camara_votacoes_orientacoes", "votacoesOrientacoes", "votacoesOrientacoes-{ano}.csv"),
        ("br_camara_votacoes_proposicoes", "votacoesProposicoes", "votacoesProposicoes-{ano}.csv"),
    ]
    for id_base, pasta, fname_tpl in series:
        for ano in ANOS:
            fname = fname_tpl.format(ano=ano)
            url = f"{CAMARA}/{pasta}/csv/{fname}"
            try_fetch(id_base, f"ano={ano}", url, "origem.csv", f"Câmara {pasta} {ano}")

    # Senado
    try_fetch(
        "br_senado_senadores_atual",
        "estatica",
        "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json",
        "origem.json",
        "Senadores em exercício",
    )
    for leg in (56, 57):
        try_fetch(
            f"br_senado_senadores_l{leg}",
            "estatica",
            f"https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/{leg}.json",
            "origem.json",
            f"Senadores legislatura {leg}",
        )
    try_fetch(
        "br_senado_votacoes_resumo",
        "estatica",
        "https://legis.senado.leg.br/dadosabertos/votacao.json",
        "origem.json",
        "Resumo de votações Senado (subconjunto — ver FONTES-PARLAMENTO)",
    )

    out = ROOT / "data" / "staging" / "parlamento_download_faltas.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(FALTAS, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FALTAS", len(FALTAS), "->", out, flush=True)
    print("DOWNLOAD_PARLAMENTO_FIM", flush=True)


if __name__ == "__main__":
    main()
