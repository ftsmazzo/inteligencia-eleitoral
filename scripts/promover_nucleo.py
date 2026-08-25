"""Copia zips do núcleo para data/raw e remove do inbox o eleitoral descartável."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(r"C:\Users\anjo_\OneDrive\Projetos-FabriaIA\inteligencia-eleitoral")
INBOX = ROOT / "inbox"
RAW = ROOT / "data" / "raw"
STAMP = date.today().isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def promote(src: Path, id_base: str, ano: str, nota: str) -> Path:
    dest_dir = RAW / id_base / f"ano={ano}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "origem.zip" if src.suffix.lower() == ".zip" else dest_dir / src.name
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    digest = sha256_file(dest)
    (dest_dir / "origem.sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id_base": id_base,
        "ano": ano,
        "copiado_em": STAMP,
        "origem_inbox": str(src.relative_to(INBOX)).replace("\\", "/"),
        "bytes": dest.stat().st_size,
        "sha256": digest,
        "nota": nota,
        "status": "bruto_completo_pendente_ciclo",
    }
    (dest_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK", id_base, ano, dest.stat().st_size)
    return dest


def rm(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        print("RMDIR", path.relative_to(INBOX))
    else:
        path.unlink()
        print("RM", path.relative_to(INBOX))


def main() -> None:
    jobs = [
        (INBOX / "ibge" / "municipios.json", "br_mun_malha_ibge", "estatica", "IBGE Localidades 5571 municípios"),
        (INBOX / "resultados" / "votacao_candidato_munzona_2014.zip", "br_mun_votacao_nominal", "2014", "TSE Brasil 27 UF+DF"),
        (INBOX / "resultados" / "votacao_candidato_munzona_2018.zip", "br_mun_votacao_nominal", "2018", "TSE Brasil"),
        (INBOX / "resultados" / "votacao_candidato_munzona_2022.zip", "br_mun_votacao_nominal", "2022", "TSE Brasil"),
        (INBOX / "resultados" / "votacao_candidato_munzona_2024.zip", "br_mun_votacao_nominal", "2024", "TSE municipal Brasil (sem DF)"),
        (INBOX / "resultados" / "detalhe_votacao_munzona_2018.zip", "br_mun_detalhe_apuracao", "2018", "TSE Brasil"),
        (INBOX / "resultados" / "detalhe_votacao_munzona_2022.zip", "br_mun_detalhe_apuracao", "2022", "TSE Brasil"),
        (INBOX / "eleitorado" / "perfil_eleitorado_2014.zip", "br_mun_eleitorado_perfil", "2014", "CSV único nacional"),
        (INBOX / "eleitorado" / "perfil_eleitorado_2018.zip", "br_mun_eleitorado_perfil", "2018", "CSV único nacional"),
        (INBOX / "eleitorado" / "perfil_eleitorado_2022.zip", "br_mun_eleitorado_perfil", "2022", "por UF"),
        (INBOX / "eleitorado" / "perfil_eleitorado_2026.zip", "br_mun_eleitorado_perfil", "2026", "cadastro 2026, não é urna"),
        (INBOX / "persona" / "consulta_cand_2018.zip", "br_cand_nominata", "2018", "TSE"),
        (INBOX / "persona" / "consulta_cand_2020.zip", "br_cand_nominata", "2020", "TSE municipal"),
        (INBOX / "persona" / "consulta_cand_2022.zip", "br_cand_nominata", "2022", "TSE"),
        (INBOX / "persona" / "consulta_cand_2024.zip", "br_cand_nominata", "2024", "TSE municipal"),
        (INBOX / "persona" / "consulta_cand_2026.zip", "br_cand_nominata", "2026", "camada viva"),
        (INBOX / "persona" / "consulta_coligacao_2018.zip", "br_cand_coligacao", "2018", "TSE"),
        (INBOX / "persona" / "consulta_coligacao_2020.zip", "br_cand_coligacao", "2020", "TSE"),
        (INBOX / "persona" / "consulta_coligacao_2022.zip", "br_cand_coligacao", "2022", "TSE"),
        (INBOX / "persona" / "consulta_coligacao_2024.zip", "br_cand_coligacao", "2024", "TSE"),
        (INBOX / "persona" / "consulta_coligacao_2026.zip", "br_cand_coligacao", "2026", "TSE"),
        (INBOX / "persona" / "consulta_vagas_2026.zip", "br_cand_vagas", "2026", "TSE"),
    ]
    copied_src: list[Path] = []
    for src, id_base, ano, nota in jobs:
        if not src.exists():
            print("SKIP missing", src)
            continue
        promote(src, id_base, ano, nota)
        copied_src.append(src)

    # eleitoral fora do recorte + duplicata descompactada NE9
    res = INBOX / "resultados"
    for year in ("1998", "2002", "2006", "2010"):
        rm(res / f"votacao_candidato_munzona_{year}")
        rm(res / f"votacao_candidato_munzona_{year}.zip")
    for year in ("2014", "2018", "2022", "2024"):
        rm(res / f"votacao_candidato_munzona_{year}")
    rm(res / "detalhe_votacao_munzona_2018")
    rm(res / "detalhe_votacao_munzona_2022")

    ele = INBOX / "eleitorado"
    for year in ("2002", "2006", "2010"):
        rm(ele / f"perfil_eleitorado_{year}.zip")
    rm(ele / "perfil_eleitorado_2018")
    rm(ele / "perfil_eleitorado_2022")

    # duplicatas já promovidas a partir de persona
    rm(INBOX / "tse" / "consulta_cand_2018.zip")
    rm(INBOX / "tse" / "consulta_cand_2022.zip")

    # zips promovidos saem do inbox (cópia está em data/raw)
    for src in copied_src:
        if src.name == "municipios.json":
            rm(src)
            continue
        rm(src)

    # emendas no meio de resultados: não é urna; fica no inbox, só tira do saco de votação
    emendas = INBOX / "emendas"
    emendas.mkdir(exist_ok=True)
    for name in ("EmendasParlamentares.zip", "202012_Despesas.zip"):
        p = res / name
        if p.exists():
            dest = emendas / name
            if dest.exists():
                rm(p)
            else:
                shutil.move(str(p), str(dest))
                print("MOVE", name, "-> emendas/")


if __name__ == "__main__":
    main()
