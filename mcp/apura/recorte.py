"""Guardas de recorte geográfico — evita falso vazio no Apura."""
from __future__ import annotations

from typing import Any

# Cargos cuja nominata filtra por município (cd_municipio_tse / cod_ibge).
_CARGOS_MUNICIPAIS = frozenset({"prefeito", "vereador"})


def _norm_cargo(cargo: str | None) -> str:
    return (cargo or "").strip().lower().replace("-", "_").replace(" ", "_")


def nominata_usa_cod_ibge(cargo: str | None) -> bool:
    c = _norm_cargo(cargo)
    return c in _CARGOS_MUNICIPAIS


def normalizar_params_mcp(method: str, params: dict[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    """Remove cod_ibge perigoso antes da call MCP (camada extra além do SQL)."""
    p = dict(params or {})
    if method != "nominata":
        return p, None
    ibge = p.get("cod_ibge")
    if ibge is None:
        return p, None
    cargo = p.get("cargo")
    if nominata_usa_cod_ibge(str(cargo) if cargo is not None else None):
        return p, None
    p.pop("cod_ibge", None)
    return p, (
        f"cod_ibge {ibge} removido na camada Apura: nominata de {cargo} recorta por UF, "
        "não por município citado na pergunta."
    )
