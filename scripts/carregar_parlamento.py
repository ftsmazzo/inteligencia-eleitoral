"""Carga parlamentar.* a partir de data/raw (Câmara + Senado) e de-para TSE 2022."""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, RAW, dsn

ANOS = [2023, 2024, 2025, 2026]


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().strip()
    for prefix in ("DR ", "DRA ", "SR ", "SRA ", "PROF ", "DEP ", "SEN "):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s: str | None) -> set[str]:
    t = norm(s)
    return {w for w in t.split() if len(w) > 1}


def names_match(a: str | None, b: str | None) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    # sobrenome único + primeiro nome
    if ta & tb and len(ta & tb) >= 2:
        return True
    return False


def as_int(v: str | None) -> int | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in {"-", "None", "null"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def as_date(v: str | None):
    if not v:
        return None
    s = v.strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def id_from_uri(uri: str | None) -> int | None:
    if not uri:
        return None
    m = re.search(r"/deputados/(\d+)", uri)
    return int(m.group(1)) if m else None


def load_deputados(conn: psycopg.Connection) -> int:
    path = RAW / "br_camara_deputados" / "estatica" / "origem.json"
    data = json.loads(path.read_text(encoding="utf-8"))["dados"]
    rows = []
    for d in data:
        i = id_from_uri(d.get("uri"))
        if i is None:
            continue
        rows.append(
            (
                i,
                d.get("nome"),
                d.get("nomeCivil"),
                (d.get("siglaSexo") or "")[:1] or None,
                (d.get("ufNascimento") or "")[:2] or None,
                d.get("municipioNascimento"),
                as_date(d.get("dataNascimento")),
                as_int(str(d.get("idLegislaturaInicial"))),
                as_int(str(d.get("idLegislaturaFinal"))),
                d.get("uri"),
            )
        )
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.deputado CASCADE")
        with cur.copy(
            """
            COPY parlamentar.deputado (
              id_deputado, nome, nome_civil, sigla_sexo, uf_nascimento, municipio_nascimento,
              data_nascimento, id_legislatura_ini, id_legislatura_fim, uri
            ) FROM STDIN
            """
        ) as copy:
            for r in rows:
                copy.write_row(r)
    print("deputado", len(rows), flush=True)
    return len(rows)


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def load_senadores(conn: psycopg.Connection) -> int:
    rows_by_id: dict[int, tuple] = {}
    for leg, folder in [
        (56, "br_senado_senadores_l56"),
        (57, "br_senado_senadores_l57"),
        (None, "br_senado_senadores_atual"),
    ]:
        path = RAW / folder / "estatica" / "origem.json"
        if not path.exists():
            print("skip sen", folder)
            continue
        root = json.loads(path.read_text(encoding="utf-8"))
        if "ListaParlamentarLegislatura" in root:
            pars = root["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"]
            default_leg = leg
        else:
            pars = root["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
            default_leg = 57
        for p in _as_list(pars):
            ident = p.get("IdentificacaoParlamentar") or {}
            sid = as_int(ident.get("CodigoParlamentar"))
            if sid is None:
                continue
            mandatos = _as_list((p.get("Mandatos") or {}).get("Mandato"))
            uf = None
            partido = None
            titular = False
            for m in mandatos:
                uf = uf or m.get("UfParlamentar")
                if (m.get("DescricaoParticipacao") or "").lower().startswith("titular"):
                    titular = True
                # partido sometimes under Mandato
                partido = partido or (m.get("Partidos") or {}).get("CodigoPartido") if False else partido
            # atual list has Partido in Identificacao
            partido = (
                (ident.get("SiglaPartidoParlamentar") or ident.get("SiglaPartido"))
                or partido
            )
            if not uf and mandatos:
                uf = mandatos[0].get("UfParlamentar")
            rows_by_id[sid] = (
                sid,
                ident.get("NomeParlamentar"),
                ident.get("NomeCompletoParlamentar"),
                partido,
                (uf or "")[:2] or None,
                default_leg,
                True if folder.endswith("atual") else titular,
                ident.get("UrlPaginaParlamentar")
                or f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{sid}",
            )
    rows = list(rows_by_id.values())
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.senador CASCADE")
        with cur.copy(
            """
            COPY parlamentar.senador (
              id_senador, nome_parlamentar, nome_completo, sg_partido, sg_uf,
              id_legislatura, em_exercicio, uri
            ) FROM STDIN
            """
        ) as copy:
            for r in rows:
                copy.write_row(r)
    print("senador", len(rows), flush=True)
    return len(rows)


def load_proposicoes(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.proposicao_autor, parlamentar.proposicao CASCADE")
    n = 0
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY parlamentar.proposicao (
              id_proposicao, sg_casa, sigla_tipo, numero, ano, ementa,
              data_apresentacao, id_situacao, descricao_situacao, uri
            ) FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_proposicoes" / f"ano={ano}" / "origem.csv"
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        pid = as_int(row.get("id"))
                        if pid is None:
                            continue
                        copy.write_row(
                            (
                                pid,
                                "CD",
                                row.get("siglaTipo"),
                                as_int(row.get("numero")),
                                as_int(row.get("ano")),
                                row.get("ementa"),
                                as_date((row.get("dataApresentacao") or "")[:10]),
                                as_int(row.get("ultimoStatus_idSituacao")),
                                row.get("ultimoStatus_descricaoSituacao"),
                                row.get("uri"),
                            )
                        )
                        n += 1
                        if n % 100_000 == 0:
                            print("  prop", n, flush=True)
    print("proposicao", n, flush=True)
    return n


def load_autores(conn: psycopg.Connection) -> int:
    n = 0
    seen: set[tuple[int, int, str]] = set()
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY parlamentar.proposicao_autor (
              id_proposicao, id_deputado, nome_autor, sg_partido, sg_uf, proponente
            ) FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_proposicoes_autores" / f"ano={ano}" / "origem.csv"
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        pid = as_int(row.get("idProposicao"))
                        if pid is None:
                            continue
                        dep = as_int(row.get("idDeputadoAutor")) or 0
                        nome = (row.get("nomeAutor") or "").strip()
                        key = (pid, dep, nome)
                        if key in seen:
                            continue
                        seen.add(key)
                        copy.write_row(
                            (
                                pid,
                                dep,
                                nome,
                                row.get("siglaPartidoAutor"),
                                (row.get("siglaUFAutor") or "")[:2] or None,
                                as_int(row.get("proponente")),
                            )
                        )
                        n += 1
    print("proposicao_autor", n, flush=True)
    return n


def load_votacoes(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.voto, parlamentar.votacao CASCADE")
    n = 0
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY parlamentar.votacao (
              id_votacao, sg_casa, data_votacao, descricao, aprovacao, ano
            ) FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_votacoes" / f"ano={ano}" / "origem.csv"
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        vid = (row.get("id") or "").strip()
                        if not vid:
                            continue
                        dh = (row.get("dataHoraRegistro") or row.get("data") or "").strip()
                        ts = None
                        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                ts = datetime.strptime(dh[:19], fmt)
                                break
                            except ValueError:
                                continue
                        copy.write_row(
                            (
                                vid,
                                "CD",
                                ts,
                                row.get("descricao") or row.get("siglaOrgao"),
                                as_int(row.get("aprovacao")),
                                ano,
                            )
                        )
                        n += 1
    print("votacao", n, flush=True)
    return n


def load_votos(conn: psycopg.Connection) -> int:
    n = 0
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY parlamentar.voto (
              id_votacao, id_deputado, voto, sg_partido, sg_uf
            ) FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_votacoes_votos" / f"ano={ano}" / "origem.csv"
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        vid = (row.get("idVotacao") or "").strip()
                        dep = as_int(row.get("deputado_id"))
                        if not vid or dep is None:
                            continue
                        copy.write_row(
                            (
                                vid,
                                dep,
                                row.get("voto"),
                                row.get("deputado_siglaPartido"),
                                (row.get("deputado_siglaUf") or "")[:2] or None,
                            )
                        )
                        n += 1
                        if n % 500_000 == 0:
                            print("  voto", n, flush=True)
    print("voto", n, flush=True)
    return n


def load_temas(conn: psycopg.Connection) -> int:
    n = 0
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.proposicao_tema")
        with cur.copy(
            """
            COPY parlamentar.proposicao_tema (id_proposicao, cod_tema, tema, relevancia)
            FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_proposicoes_temas" / f"ano={ano}" / "origem.csv"
                if not path.exists():
                    continue
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        uri = row.get("uriProposicao") or ""
                        m = re.search(r"/proposicoes/(\d+)", uri)
                        pid = as_int(m.group(1) if m else row.get("id"))
                        cod = as_int(row.get("codTema"))
                        if pid is None or cod is None:
                            continue
                        copy.write_row((pid, cod, row.get("tema"), row.get("relevancia")))
                        n += 1
    print("proposicao_tema", n, flush=True)
    return n


def load_orientacoes(conn: psycopg.Connection) -> int:
    n = 0
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.orientacao")
        with cur.copy(
            """
            COPY parlamentar.orientacao (id_votacao, sigla_bancada, orientacao, sigla_orgao)
            FROM STDIN
            """
        ) as copy:
            for ano in ANOS:
                path = RAW / "br_camara_votacoes_orientacoes" / f"ano={ano}" / "origem.csv"
                if not path.exists():
                    continue
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        vid = (row.get("idVotacao") or "").strip()
                        if not vid:
                            continue
                        banc = (row.get("siglaBancada") or "").strip()
                        copy.write_row(
                            (
                                vid,
                                banc,
                                row.get("orientacao"),
                                row.get("siglaOrgao"),
                            )
                        )
                        n += 1
    print("orientacao", n, flush=True)
    return n


def build_depara(conn: psycopg.Connection) -> int:
    """Liga eleitos 2022 (dep fed / senador) a ids da Casa por UF + nome normalizado."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parlamentar.depara_tse")

        # perfil deputado a partir dos votos (UF/partido vigentes na legislatura)
        cur.execute(
            """
            SELECT id_deputado,
                   mode() WITHIN GROUP (ORDER BY sg_uf) AS sg_uf,
                   mode() WITHIN GROUP (ORDER BY sg_partido) AS sg_partido
            FROM parlamentar.voto
            WHERE sg_uf IS NOT NULL
            GROUP BY id_deputado
            """
        )
        perfil = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

        cur.execute(
            "SELECT id_deputado, nome, nome_civil FROM parlamentar.deputado"
        )
        deps = cur.fetchall()
        # index: (uf, norm_nome) -> id
        idx: dict[tuple[str, str], int] = {}
        for i, nome, civil in deps:
            uf = (perfil.get(i) or (None, None))[0]
            if not uf:
                continue
            for label in (nome, civil):
                k = (uf, norm(label))
                if k[1]:
                    idx[k] = i

        cur.execute(
            """
            SELECT DISTINCT ON (v.sq_candidato)
              v.sq_candidato, v.sg_uf, v.sg_partido, v.nm_urna, c.nm_candidato
            FROM eleicao.votacao v
            LEFT JOIN eleicao.candidatura c
              ON c.ano = v.ano AND c.sq_candidato = v.sq_candidato
            WHERE v.ano = 2022 AND v.cd_cargo = 6
              AND (v.ds_sit_tot_turno = 'ELEITO'
                   OR v.ds_sit_tot_turno = 'ELEITO POR QP'
                   OR v.ds_sit_tot_turno ~* '^ELEITO POR M')
            ORDER BY v.sq_candidato, v.nr_turno DESC
            """
        )
        n = 0
        for sq, uf, partido, urna, completo in cur.fetchall():
            hit = None
            for label in (urna, completo):
                hit = idx.get((uf, norm(label)))
                if hit:
                    break
            if not hit:
                continue
            cur.execute(
                """
                INSERT INTO parlamentar.depara_tse (casa, id_casa, ano_eleicao, sq_candidato, metodo, confianca)
                VALUES ('CD', %s, 2022, %s, 'uf+nome_norm', 0.80)
                ON CONFLICT DO NOTHING
                """,
                (hit, sq),
            )
            n += 1

        # senadores titulares L57
        cur.execute(
            "SELECT id_senador, nome_parlamentar, nome_completo, sg_uf, sg_partido FROM parlamentar.senador"
        )
        sen_rows = cur.fetchall()
        sidx: dict[tuple[str, str], int] = {}
        for i, np, nc, uf, _sp in sen_rows:
            if not uf:
                continue
            for label in (np, nc):
                k = (uf, norm(label))
                if k[1]:
                    sidx[k] = i

        cur.execute(
            """
            SELECT DISTINCT ON (v.sq_candidato)
              v.sq_candidato, v.sg_uf, v.nm_urna, c.nm_candidato
            FROM eleicao.votacao v
            LEFT JOIN eleicao.candidatura c
              ON c.ano = v.ano AND c.sq_candidato = v.sq_candidato
            WHERE v.ano = 2022 AND v.cd_cargo = 5
              AND v.ds_sit_tot_turno = 'ELEITO'
            ORDER BY v.sq_candidato, v.nr_turno DESC
            """
        )
        ns = 0
        for sq, uf, urna, completo in cur.fetchall():
            hit = None
            metodo = "uf+nome_norm"
            conf = 0.80
            for label in (urna, completo):
                hit = sidx.get((uf, norm(label)))
                if hit:
                    break
            if not hit:
                cands = [(sid, np, nc, sp) for sid, np, nc, su, sp in sen_rows if su == uf]
                for sid, np, nc, _sp in cands:
                    if names_match(urna, np) or names_match(urna, nc) or names_match(completo, np):
                        hit = sid
                        metodo = "uf+tokens"
                        conf = 0.65
                        break
            if not hit:
                continue
            cur.execute(
                """
                INSERT INTO parlamentar.depara_tse (casa, id_casa, ano_eleicao, sq_candidato, metodo, confianca)
                VALUES ('SF', %s, 2022, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (hit, sq, metodo, conf),
            )
            ns += 1
    print("depara CD", n, "SF", ns, flush=True)
    return n + ns


def main() -> None:
    url = dsn()
    patch = (ROOT / "sql" / "patch_parlamento.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(patch)
    with psycopg.connect(url) as conn:
        load_deputados(conn)
        load_senadores(conn)
        load_proposicoes(conn)
        load_autores(conn)
        load_votacoes(conn)
        load_votos(conn)
        load_temas(conn)
        load_orientacoes(conn)
        build_depara(conn)
        conn.commit()
    print("CARGA_PARLAMENTO_FIM", flush=True)


if __name__ == "__main__":
    main()
