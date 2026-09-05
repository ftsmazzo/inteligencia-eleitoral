"""API HTTP do Mapa sob /apura/api/mapa — JWT + campanha ativa."""
from __future__ import annotations

import asyncio
import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

import httpx
import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

from apura.auth import decodificar_jwt, usuario_por_id
from mapa import store
from mapa.schema import ensure_schema

router = APIRouter(prefix="/apura/api/mapa", tags=["mapa"])


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGENTE_DATABASE_URL")


def _ddl_url() -> str | None:
    return os.environ.get("POSTGRES_ADMIN_URL") or _db_url()


def _ensure() -> None:
    try:
        ensure_schema()
    except Exception as exc:
        # Mensagem limpa; deadlock raro após advisory lock + retry
        raise HTTPException(503, f"Falha ao preparar Mapa ({exc})") from exc


@contextmanager
def _db() -> Iterator[psycopg.Connection]:
    _ensure()
    url = _ddl_url() or _db_url()
    if not url:
        raise HTTPException(503, "Banco indisponível")
    with psycopg.connect(url) as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticação necessária")
    return authorization[7:].strip()


def _usuario(authorization: str | None = Header(default=None)) -> tuple[str, str, str]:
    payload = decodificar_jwt(_bearer(authorization))
    with _db() as conn:
        return usuario_por_id(conn, payload["sub"])


def _campanha(user: tuple[str, str, str]) -> tuple[str, str]:
    with _db() as conn:
        row = store.campanha_do_usuario(conn, user[0])
    if not row:
        raise HTTPException(403, "Usuário sem campanha — Operar uma campanha primeiro")
    return row


class NotaIn(BaseModel):
    texto: str = Field(default="", max_length=20000)


class PontoIn(BaseModel):
    cod_ibge: int | None = None
    nome: str | None = None
    lat: float
    lng: float
    ordem: int = 0


class CaravanaIn(BaseModel):
    nome: str = Field(default="Carreata", max_length=200)
    pontos: list[PontoIn] = Field(default_factory=list)
    calcular_rota: bool = True


class CaravanaPatch(BaseModel):
    nome: str | None = Field(default=None, max_length=200)
    pontos: list[PontoIn] | None = None
    calcular_rota: bool = True


async def _rota_osrm(pontos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Rota rodoviária via OSRM público; None se falhar (UI usa linha reta)."""
    if len(pontos) < 2:
        return None
    coords = ";".join(f"{p['lng']},{p['lat']}" for p in pontos)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(url, params={"overview": "full", "geometries": "geojson"})
        if r.status_code >= 400:
            return None
        data = r.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        geom = routes[0].get("geometry")
        return {
            "type": "Feature",
            "properties": {
                "distance_m": routes[0].get("distance"),
                "duration_s": routes[0].get("duration"),
                "fonte": "osrm",
            },
            "geometry": geom,
        }
    except Exception:
        return None


@router.get("/municipios")
def municipios(
    uf: str = "AP",
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    _campanha(user)
    with _db() as conn:
        linhas = store.listar_municipios(conn, uf=uf)
    return {"status": "ok", "uf": (uf or "AP").upper()[:2], "linhas": linhas}


@router.get("/notas")
def notas(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        return {"status": "ok", "linhas": store.listar_notas(conn, camp[0])}


@router.put("/notas/{cod_ibge}")
def salvar_nota(
    cod_ibge: int,
    body: NotaIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        item = store.upsert_nota(
            conn,
            campanha_id=camp[0],
            cod_ibge=cod_ibge,
            texto=body.texto,
            usuario_id=user[0],
        )
    return {"status": "ok", "item": item}


@router.delete("/notas/{cod_ibge}")
def delete_nota(
    cod_ibge: int,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        ok = store.apagar_nota(conn, campanha_id=camp[0], cod_ibge=cod_ibge)
    if not ok:
        raise HTTPException(404, "Nota não encontrada")
    return {"status": "ok"}


class RotaPreviewIn(BaseModel):
    pontos: list[PontoIn] = Field(default_factory=list)


class GeocodeCepsIn(BaseModel):
    """Lista de CEPs (e opcionalmente endereços livres, 1 por linha)."""
    ceps: list[str] = Field(default_factory=list, max_length=40)
    uf: str = Field(default="AP", max_length=2)


def _normalizar_cep(raw: str) -> str | None:
    digitos = "".join(c for c in (raw or "") if c.isdigit())
    return digitos if len(digitos) == 8 else None


async def _geocode_cep_um(client: httpx.AsyncClient, cep: str, uf: str) -> dict[str, Any]:
    """BrasilAPI (coords) → ViaCEP+Nominatim se faltar ponto."""
    out: dict[str, Any] = {
        "cep": cep,
        "ok": False,
        "lat": None,
        "lng": None,
        "nome": None,
        "fonte": None,
        "erro": None,
    }
    try:
        r = await client.get(f"https://brasilapi.com.br/api/cep/v2/{cep}")
        if r.status_code == 200:
            data = r.json()
            state = (data.get("state") or "").upper()
            if uf and state and state != uf.upper():
                out["erro"] = f"CEP fora de {uf.upper()} ({state})"
                return out
            city = data.get("city") or ""
            street = data.get("street") or ""
            neigh = data.get("neighborhood") or ""
            label = " · ".join(x for x in (street, neigh, city) if x) or f"CEP {cep}"
            loc = (data.get("location") or {}).get("coordinates") or {}
            lat_s, lng_s = loc.get("latitude"), loc.get("longitude")
            if lat_s not in (None, "") and lng_s not in (None, ""):
                out.update(
                    ok=True,
                    lat=float(lat_s),
                    lng=float(lng_s),
                    nome=label,
                    fonte="brasilapi",
                    cod_ibge=int((data.get("ibge") or {}).get("city") or 0) or None,
                )
                return out
            # Sem coords: monta query Nominatim
            q = ", ".join(x for x in (street, neigh, city, state or uf, "Brasil") if x)
            out["nome"] = label
            nr = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "br",
                },
                headers={"User-Agent": "ApuraMapa/1.0 (campanha-eleitoral)"},
            )
            if nr.status_code == 200:
                hits = nr.json() or []
                if hits:
                    out.update(
                        ok=True,
                        lat=float(hits[0]["lat"]),
                        lng=float(hits[0]["lon"]),
                        fonte="nominatim",
                    )
                    return out
            out["erro"] = "CEP encontrado, sem coordenada"
            return out
        if r.status_code == 404:
            out["erro"] = "CEP não encontrado"
            return out
        out["erro"] = f"BrasilAPI HTTP {r.status_code}"
        return out
    except Exception as exc:
        out["erro"] = str(exc)[:200]
        return out


async def _geocode_endereco(
    client: httpx.AsyncClient, texto: str, uf: str
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "cep": None,
        "ok": False,
        "lat": None,
        "lng": None,
        "nome": texto,
        "fonte": None,
        "erro": None,
    }
    q = f"{texto}, {uf}, Brasil" if uf else f"{texto}, Brasil"
    try:
        nr = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "json",
                "limit": 1,
                "countrycodes": "br",
            },
            headers={"User-Agent": "ApuraMapa/1.0 (campanha-eleitoral)"},
        )
        if nr.status_code == 200:
            hits = nr.json() or []
            if hits:
                out.update(
                    ok=True,
                    lat=float(hits[0]["lat"]),
                    lng=float(hits[0]["lon"]),
                    nome=hits[0].get("display_name") or texto,
                    fonte="nominatim",
                )
                return out
        out["erro"] = "Endereço não encontrado"
        return out
    except Exception as exc:
        out["erro"] = str(exc)[:200]
        return out


@router.post("/geocode-ceps")
async def geocode_ceps(
    body: GeocodeCepsIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    """Resolve CEPs (e linhas de endereço) → pontos lat/lng para carreata."""
    _campanha(user)
    uf = (body.uf or "AP").upper()[:2]
    linhas = [str(x).strip() for x in (body.ceps or []) if str(x).strip()]
    if not linhas:
        return {"status": "vazio", "mensagem": "informe ao menos 1 CEP", "pontos": [], "falhas": []}

    pontos: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for raw in linhas[:40]:
            # "68900-073", "68900073 Centro" ou endereço livre
            m = re.search(r"\d{5}-?\d{3}", raw)
            cep = _normalizar_cep(m.group(0)) if m else None
            if cep:
                hit = await _geocode_cep_um(client, cep, uf)
            else:
                hit = await _geocode_endereco(client, raw, uf)
            if hit.get("ok") and hit.get("lat") is not None and hit.get("lng") is not None:
                pontos.append(
                    {
                        "lat": hit["lat"],
                        "lng": hit["lng"],
                        "ordem": len(pontos),
                        "nome": hit.get("nome") or f"Parada {len(pontos) + 1}",
                        "cod_ibge": hit.get("cod_ibge"),
                        "cep": hit.get("cep") or cep,
                        "fonte": hit.get("fonte"),
                    }
                )
            else:
                falhas.append({"linha": raw, "erro": hit.get("erro") or "falha"})
            # Nominatim pede ~1 req/s
            if hit.get("fonte") == "nominatim" or not hit.get("ok"):
                await asyncio.sleep(1.05)

    return {
        "status": "ok",
        "uf": uf,
        "pontos": pontos,
        "falhas": falhas,
        "mensagem": f"{len(pontos)} ponto(s) · {len(falhas)} falha(s)",
    }


@router.post("/rota-preview")
async def rota_preview(
    body: RotaPreviewIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    """Prévia de rota rodoviária (OSRM) sem gravar caravana."""
    _campanha(user)
    pontos = [p.model_dump() for p in body.pontos]
    if len(pontos) < 2:
        return {"status": "vazio", "mensagem": "informe ao menos 2 pontos"}
    rota = await _rota_osrm(pontos)
    if not rota:
        return {
            "status": "ok",
            "rota_geojson": None,
            "fallback": "linha_reta",
            "mensagem": "OSRM indisponível — prévia em linha reta no cliente",
        }
    return {"status": "ok", "rota_geojson": rota, "fallback": None}


@router.get("/caravanas")
def caravanas(user: tuple[str, str, str] = Depends(_usuario)) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        return {"status": "ok", "linhas": store.listar_caravanas(conn, camp[0])}


@router.post("/caravanas")
async def criar_caravana(
    body: CaravanaIn,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    pontos = [p.model_dump() for p in body.pontos]
    for i, p in enumerate(pontos):
        p["ordem"] = p.get("ordem") if p.get("ordem") is not None else i
    pontos.sort(key=lambda x: int(x.get("ordem") or 0))
    rota = await _rota_osrm(pontos) if body.calcular_rota else None
    with _db() as conn:
        item = store.salvar_caravana(
            conn,
            campanha_id=camp[0],
            nome=body.nome,
            pontos=pontos,
            rota_geojson=rota,
            usuario_id=user[0],
        )
    return {"status": "ok", "item": item}


@router.patch("/caravanas/{caravana_id}")
async def patch_caravana(
    caravana_id: str,
    body: CaravanaPatch,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        atuais = store.listar_caravanas(conn, camp[0])
        found = next((c for c in atuais if c["id"] == caravana_id), None)
        if not found:
            raise HTTPException(404, "Caravana não encontrada")
        nome = body.nome if body.nome is not None else found["nome"]
        pontos = (
            [p.model_dump() for p in body.pontos]
            if body.pontos is not None
            else found["pontos"]
        )
        for i, p in enumerate(pontos):
            p["ordem"] = p.get("ordem") if p.get("ordem") is not None else i
        pontos.sort(key=lambda x: int(x.get("ordem") or 0))
        rota = found.get("rota_geojson")
        if body.calcular_rota and body.pontos is not None:
            rota = await _rota_osrm(pontos)
        try:
            item = store.salvar_caravana(
                conn,
                campanha_id=camp[0],
                nome=nome,
                pontos=pontos,
                rota_geojson=rota,
                usuario_id=user[0],
                caravana_id=caravana_id,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
    return {"status": "ok", "item": item}


@router.delete("/caravanas/{caravana_id}")
def delete_caravana(
    caravana_id: str,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    camp = _campanha(user)
    with _db() as conn:
        ok = store.apagar_caravana(conn, campanha_id=camp[0], caravana_id=caravana_id)
    if not ok:
        raise HTTPException(404, "Caravana não encontrada")
    return {"status": "ok"}


@router.get("/calor")
def calor(
    ano: int = 2022,
    turno: int = 0,
    user: tuple[str, str, str] = Depends(_usuario),
) -> dict[str, Any]:
    """Mapa de calor oficial (município) + tabela por zona. Trilha A."""
    camp = _campanha(user)
    with _db() as conn:
        return store.calor_urna(
            conn,
            campanha_id=camp[0],
            ano=ano,
            turno=turno if turno > 0 else None,
        )


@router.get("/caravanas/{caravana_id}/export.html")
def export_caravana_html(
    caravana_id: str,
    user: tuple[str, str, str] = Depends(_usuario),
) -> Any:
    """HTML autocontido da carreata (paradas + trajeto) para baixar/imprimir."""
    camp = _campanha(user)
    with _db() as conn:
        itens = store.listar_caravanas(conn, camp[0])
    found = next((c for c in itens if c["id"] == caravana_id), None)
    if not found:
        raise HTTPException(404, "Caravana não encontrada")
    html = _html_caravana(found)
    return HTMLResponse(
        content=html,
        headers={
            "Content-Disposition": f'attachment; filename="carreata-{caravana_id[:8]}.html"'
        },
    )


def _html_caravana(item: dict[str, Any]) -> str:
    import json as _json

    nome = (item.get("nome") or "Carreata").replace("<", "")
    pontos = item.get("pontos") or []
    rota = item.get("rota_geojson")
    props = (rota or {}).get("properties") or {} if isinstance(rota, dict) else {}
    km = props.get("distance_m")
    dur = props.get("duration_s")
    meta = []
    if km is not None:
        meta.append(f"{float(km) / 1000:.1f} km")
    if dur is not None:
        meta.append(f"~{int(round(float(dur) / 60))} min")
    meta_s = " · ".join(meta) if meta else "trajeto salvo"
    pontos_js = _json.dumps(pontos, ensure_ascii=False)
    rota_js = _json.dumps(rota, ensure_ascii=False) if rota else "null"
    lis = "".join(
        f"<li><b>{i + 1}.</b> {(p.get('nome') or 'Parada')} "
        f"<span>({p.get('lat')}, {p.get('lng')})"
        f"{(' · CEP ' + str(p['cep'])) if p.get('cep') else ''}</span></li>"
        for i, p in enumerate(pontos)
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{nome} · Apura Mapa</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  body{{margin:0;font-family:system-ui,sans-serif;color:#0c1222;background:#f4f7fa}}
  header{{padding:16px 20px;background:#0d4f4a;color:#fff}}
  header h1{{margin:0;font-size:1.25rem}}
  header p{{margin:6px 0 0;opacity:.9;font-size:.9rem}}
  #map{{height:55vh;min-height:320px;border-bottom:1px solid #cfd8e3}}
  main{{padding:16px 20px 40px;max-width:720px}}
  ol{{padding-left:1.2rem;line-height:1.55}}
  li span{{color:#5a6a7a;font-size:.85rem}}
  .fonte{{margin-top:24px;font-size:.8rem;color:#5a6a7a}}
</style></head><body>
<header><h1>{nome}</h1><p>Carreata roteirizada · {meta_s}</p></header>
<div id="map"></div>
<main>
  <h2>Paradas / endereços</h2>
  <ol>{lis or "<li>Sem pontos</li>"}</ol>
  <p class="fonte">Gerado pelo Apura Mapa · rota OSRM quando disponível · não é cifra eleitoral.</p>
</main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const pontos = {pontos_js};
const rota = {rota_js};
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19, attribution: '&copy; OpenStreetMap'
}}).addTo(map);
const latlngs = pontos.map(p => [p.lat, p.lng]);
pontos.forEach((p, i) => {{
  L.marker([p.lat, p.lng]).addTo(map).bindPopup((i+1)+'. '+(p.nome||'Parada'));
}});
if (rota && rota.geometry) {{
  L.geoJSON(rota, {{ style: {{ color: '#0d4f4a', weight: 5 }} }}).addTo(map);
}} else if (latlngs.length >= 2) {{
  L.polyline(latlngs, {{ color: '#0d4f4a', weight: 4, dashArray: '6 8' }}).addTo(map);
}}
if (latlngs.length) map.fitBounds(latlngs, {{ padding: [40, 40] }});
else map.setView([0.0349, -51.0694], 11);
</script></body></html>"""
