"""Plano estratégico HTML autocontido (artefato visual de campanha)."""
from __future__ import annotations

import html as html_module
import re
from datetime import datetime, timezone
from typing import Any


def _esc(s: str) -> str:
    return html_module.escape(s or "", quote=True)


def _split_eixos(raw: str) -> list[dict[str, str]]:
    """Aceita texto livre: linhas '- Título: detalhe' ou blocos separados por \\n\\n."""
    text = (raw or "").strip()
    if not text:
        return []
    eixos: list[dict[str, str]] = []
    # tenta JSON-ish "titulo|corpo" por linha
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        ln = re.sub(r"^[-*•]\s*", "", ln)
        if ":" in ln[:80]:
            tit, _, corpo = ln.partition(":")
            eixos.append({"titulo": tit.strip()[:80], "corpo": corpo.strip()[:800]})
        else:
            eixos.append({"titulo": f"Eixo {len(eixos)+1}", "corpo": ln[:800]})
    if len(eixos) == 1 and "\n\n" in text:
        eixos = []
        for i, bloco in enumerate(text.split("\n\n")):
            bloco = bloco.strip()
            if not bloco:
                continue
            linhas = bloco.splitlines()
            tit = re.sub(r"^[-*#]+\s*", "", linhas[0]).strip()[:80]
            corpo = "\n".join(linhas[1:]).strip() if len(linhas) > 1 else ""
            eixos.append({"titulo": tit or f"Eixo {i+1}", "corpo": corpo[:800]})
    return eixos[:8]


def montar_plano_html(
    *,
    titulo: str,
    eixos_raw: str,
    nosso: str = "",
    rival: str = "",
    contexto: str = "",
    leituras: str = "",
    proximo: str = "",
) -> str:
    """HTML5 autocontido — plano / mapa estratégico visual."""
    titulo = (titulo or "Plano estratégico").strip()[:120]
    nosso = (nosso or "").strip()[:80]
    rival = (rival or "").strip()[:80]
    eixos = _split_eixos(eixos_raw)
    if not eixos:
        eixos = [{"titulo": "Direção", "corpo": (eixos_raw or "Definir eixos com a coordenação.")[:800]}]
    when = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    cards = []
    for i, e in enumerate(eixos):
        cards.append(
            f"""
      <article class="eixo">
        <div class="num">{i + 1:02d}</div>
        <h3>{_esc(e['titulo'])}</h3>
        <p>{_esc(e['corpo']) or '—'}</p>
      </article>"""
        )
    vs = ""
    if nosso or rival:
        vs = f"""
    <section class="vs">
      <div class="lado nosso"><span>Nós</span><strong>{_esc(nosso or '—')}</strong></div>
      <div class="x">×</div>
      <div class="lado rival"><span>Rival</span><strong>{_esc(rival or '—')}</strong></div>
    </section>"""
    ctx_html = f"<p class='ctx'>{_esc(contexto[:1200])}</p>" if contexto.strip() else ""
    leit_html = ""
    if leituras.strip():
        leit_html = f"""
    <section class="bloco">
      <h2>Leitura</h2>
      <p>{_esc(leituras[:2000])}</p>
    </section>"""
    prox_html = ""
    if proximo.strip():
        prox_html = f"""
    <section class="bloco prox">
      <h2>Próximo passo</h2>
      <p>{_esc(proximo[:800])}</p>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(titulo)} · Apura</title>
<style>
  :root {{
    --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --brand:#0d4f4a; --brand2:#1a7a72; --sand:#f6f3ee;
    --rival:#9a3412; --card:#fff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin:0; font-family: "Segoe UI", system-ui, sans-serif;
    color:var(--ink); background:
      radial-gradient(900px 400px at 10% -10%, #d8efe9 0%, transparent 55%),
      radial-gradient(700px 360px at 100% 0%, #fde8d8 0%, transparent 50%),
      var(--sand);
    line-height:1.45;
  }}
  .wrap {{ max-width:980px; margin:0 auto; padding:28px 18px 48px; }}
  header.hero {{
    background: linear-gradient(135deg, var(--brand), var(--brand2));
    color:#fff; border-radius:22px; padding:28px 30px; margin-bottom:22px;
    box-shadow: 0 18px 40px rgba(13,79,74,.25);
  }}
  .kicker {{ font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; opacity:.85; font-weight:700; }}
  h1 {{ font-size:1.7rem; margin:8px 0 6px; font-weight:700; letter-spacing:-.02em; }}
  .meta {{ font-size:.88rem; opacity:.9; }}
  .vs {{
    display:grid; grid-template-columns:1fr auto 1fr; gap:12px; align-items:center;
    margin:18px 0 8px;
  }}
  .lado {{ background:rgba(255,255,255,.12); border-radius:14px; padding:12px 14px; }}
  .lado span {{ display:block; font-size:.7rem; text-transform:uppercase; letter-spacing:.08em; opacity:.8; }}
  .lado strong {{ font-size:1.05rem; }}
  .lado.rival {{ background:rgba(154,52,18,.35); }}
  .x {{ font-size:1.4rem; font-weight:800; opacity:.9; }}
  .ctx {{ margin:14px 0 0; opacity:.95; }}
  .grade {{
    display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
    gap:14px; margin:18px 0;
  }}
  .eixo {{
    background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:16px 16px 18px; position:relative;
    box-shadow: 0 8px 24px rgba(15,23,42,.05);
  }}
  .eixo .num {{
    font-size:.7rem; font-weight:800; color:var(--brand2); letter-spacing:.08em;
  }}
  .eixo h3 {{ margin:6px 0 8px; font-size:1.05rem; }}
  .eixo p {{ margin:0; color:#334155; font-size:.92rem; white-space:pre-wrap; }}
  .bloco {{
    background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:18px 20px; margin-top:14px;
  }}
  .bloco h2 {{ margin:0 0 8px; font-size:1.05rem; color:var(--brand); }}
  .bloco.prox {{ border-left:4px solid var(--brand2); }}
  footer {{ margin-top:22px; font-size:.78rem; color:var(--muted); }}
  @media print {{
    body {{ background:#fff; }}
    header.hero {{ box-shadow:none; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="kicker">Apura · plano estratégico</div>
      <h1>{_esc(titulo)}</h1>
      <div class="meta">Artefato de campanha · {_esc(when)} · não substitui cifra oficial</div>
      {vs}
      {ctx_html}
    </header>
    <section class="grade">
      {"".join(cards)}
    </section>
    {leit_html}
    {prox_html}
    <footer>Gerado pelo Apura. Indício/artefato — cruzar com Trilha A antes de decisão de urna.</footer>
  </div>
</body>
</html>
"""


def enriquecer_params_do_ctx(params: dict[str, Any], campanha_ctx: str = "") -> dict[str, Any]:
    """Preenche nosso/rival a partir do contexto injetado, se faltarem."""
    out = dict(params or {})
    ctx = campanha_ctx or ""
    if not (out.get("nosso") or "").strip():
        m = re.search(
            r"(?:Nosso candidato|candidato monitorado)[^\n:]{0,40}:\s*([^\n(]+)",
            ctx,
            re.I,
        )
        if m:
            out["nosso"] = m.group(1).strip()[:80]
    if not (out.get("rival") or "").strip():
        m = re.search(r"Rival\(is\) de campanha[^:\n]*:\s*([^\n;]+)", ctx, re.I)
        if m and "ainda não" not in m.group(1).lower():
            out["rival"] = m.group(1).strip()[:80]
    return out
