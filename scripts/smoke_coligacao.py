import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import dsn
import psycopg

with psycopg.connect(dsn()) as c:
    r = c.execute(
        "SELECT api.coligacao(%s,%s,%s,%s,%s,%s,%s)",
        (2022, "deputado_federal", "SP", None, "PL", None, 10),
    ).fetchone()[0]
    print(json.dumps(r, ensure_ascii=False, indent=2)[:800])
