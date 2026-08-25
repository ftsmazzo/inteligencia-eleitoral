"""Limpa inbox eleitoral após cópia para data/raw. Tenta rd /s /q no Windows."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

INBOX = Path(r"C:\Users\anjo_\OneDrive\Projetos-FabriaIA\inteligencia-eleitoral\inbox")


def wipe(path: Path) -> None:
    if not path.exists():
        print("gone", path.name)
        return
    cmd = ["cmd", "/c", "attrib", "-R", "-S", "-H", str(path), "/S", "/D"]
    subprocess.run(cmd, capture_output=True)
    if path.is_dir():
        r = subprocess.run(["cmd", "/c", "rd", "/s", "/q", str(path)], capture_output=True, text=True)
        if path.exists():
            try:
                shutil.rmtree(path, ignore_errors=True)
            except OSError as e:
                print("FAIL DIR", path, e)
                return
        print("RD", path.name, "ok" if not path.exists() else "AINDA LA")
    else:
        try:
            path.unlink()
            print("DEL", path.name)
        except OSError:
            r = subprocess.run(["cmd", "/c", "del", "/f", "/q", str(path)], capture_output=True, text=True)
            print("DEL", path.name, "ok" if not path.exists() else r.stderr)


def main() -> None:
    res = INBOX / "resultados"
    ele = INBOX / "eleitorado"
    for year in ("1998", "2002", "2006", "2010"):
        wipe(res / f"votacao_candidato_munzona_{year}")
        wipe(res / f"votacao_candidato_munzona_{year}.zip")
    for year in ("2014", "2018", "2022", "2024"):
        wipe(res / f"votacao_candidato_munzona_{year}")
        wipe(res / f"votacao_candidato_munzona_{year}.zip")
    wipe(res / "detalhe_votacao_munzona_2018")
    wipe(res / "detalhe_votacao_munzona_2022")
    wipe(res / "detalhe_votacao_munzona_2018.zip")
    wipe(res / "detalhe_votacao_munzona_2022.zip")

    emendas = INBOX / "emendas"
    emendas.mkdir(exist_ok=True)
    for name in ("EmendasParlamentares.zip", "202012_Despesas.zip"):
        p = res / name
        if p.exists():
            dest = emendas / name
            if dest.exists():
                wipe(p)
            else:
                shutil.move(str(p), str(dest))
                print("MOVE", name)

    for year in ("2002", "2006", "2010", "2014", "2018", "2022", "2026"):
        wipe(ele / f"perfil_eleitorado_{year}.zip")
    wipe(ele / "perfil_eleitorado_2018")
    wipe(ele / "perfil_eleitorado_2022")

    wipe(INBOX / "tse" / "consulta_cand_2018.zip")
    wipe(INBOX / "tse" / "consulta_cand_2022.zip")
    wipe(INBOX / "ibge" / "municipios.json")

    persona = INBOX / "persona"
    for name in [
        "consulta_cand_2018.zip",
        "consulta_cand_2020.zip",
        "consulta_cand_2022.zip",
        "consulta_cand_2024.zip",
        "consulta_cand_2026.zip",
        "consulta_coligacao_2018.zip",
        "consulta_coligacao_2020.zip",
        "consulta_coligacao_2022.zip",
        "consulta_coligacao_2024.zip",
        "consulta_coligacao_2026.zip",
        "consulta_vagas_2026.zip",
    ]:
        wipe(persona / name)


if __name__ == "__main__":
    main()
