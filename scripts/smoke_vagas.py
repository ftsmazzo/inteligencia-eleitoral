import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import dsn
import psycopg

with psycopg.connect(dsn()) as c:
    print("por ano", c.execute("select ano, count(*), sum(qt_vagas) from eleicao.vagas group by 1 order by 1").fetchall())
    r = c.execute(
        "SELECT api.vagas(%s,%s,%s,%s,%s)",
        (2022, "deputado_federal", "SP", None, 10),
    ).fetchone()[0]
    print("api dep fed SP 2022", json.dumps(r, ensure_ascii=False))
    r2 = c.execute(
        "SELECT api.vagas(%s,%s,%s,%s,%s)",
        (2014, "deputado_federal", "SP", None, 5),
    ).fetchone()[0]
    print("api dep fed SP 2014", json.dumps(r2, ensure_ascii=False))
    r3 = c.execute(
        "SELECT api.vagas(%s,%s,%s,%s,%s)",
        (2024, "vereador", "SP", None, 3),
    ).fetchone()[0]
    print("api ver SP 2024 n", len(r3.get("linhas", [])), "status", r3.get("status"))
