"""Linha partidária e regiões — expansão automática (espelho de ref.partido_linha)."""
from __future__ import annotations

# Famílias alinhadas a sql/patch_partido_linha.sql
_LINHAS: dict[str, tuple[str, ...]] = {
    "pl": ("PL", "PR", "PSL"),
    "mdb": ("MDB", "PMDB"),
    "uniao": ("UNIÃO", "UNIAO", "DEM", "PFL"),
    "republicanos": ("REPUBLICANOS", "PRB"),
    "pp": ("PP", "PPB"),
    "podemos": ("PODEMOS", "PODE", "PTN", "PHS"),
    "cidadania": ("CIDADANIA", "PPS"),
    "avante": ("AVANTE", "PT do B", "PTDOB"),
    "solidariedade": ("SOLIDARIEDADE", "SD"),
    "patriota": ("PATRIOTA", "PEN"),
    "agir": ("AGIR", "PTC"),
    "dc": ("DC", "PSDC"),
    "rede": ("REDE",),
    "novo": ("NOVO",),
    "pt": ("PT",),
    "psdb": ("PSDB",),
    "pdt": ("PDT",),
    "psb": ("PSB",),
    "pcdob": ("PCdoB", "PCDOB"),
    "psol": ("PSOL",),
    "pv": ("PV",),
    "pcb": ("PCB",),
    "pstu": ("PSTU",),
    "pco": ("PCO",),
    "up": ("UP",),
    "mobiliza": ("MOBILIZA", "PPL"),
}

_SG_TO_LINHA: dict[str, str] = {}
for _lid, _sigs in _LINHAS.items():
    for _sg in _sigs:
        _SG_TO_LINHA[_sg.upper()] = _lid

_REGIOES: dict[str, tuple[str, ...]] = {
    "NORDESTE": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "NE": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "NORTE": ("AC", "AP", "AM", "PA", "RO", "RR", "TO"),
    "SUDESTE": ("ES", "MG", "RJ", "SP"),
    "SUL": ("PR", "RS", "SC"),
    "CENTRO-OESTE": ("DF", "GO", "MS", "MT"),
    "CENTRO_OESTE": ("DF", "GO", "MS", "MT"),
    "CENTROOESTE": ("DF", "GO", "MS", "MT"),
    "CO": ("DF", "GO", "MS", "MT"),
}


def siglas_equivalentes(sg: str | None) -> list[str]:
    if not sg or not str(sg).strip():
        return []
    key = str(sg).strip().upper()
    lid = _SG_TO_LINHA.get(key)
    if not lid:
        return [key]
    return list(_LINHAS[lid])


def eh_regiao(uf: str | None) -> bool:
    if not uf:
        return False
    return str(uf).strip().upper() in _REGIOES


def ufs_da_regiao(uf: str | None) -> list[str]:
    if not uf:
        return []
    return list(_REGIOES.get(str(uf).strip().upper(), ()))
