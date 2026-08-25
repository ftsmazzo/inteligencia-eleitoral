import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import dsn
import psycopg


def main() -> None:
    with psycopg.connect(dsn()) as c:
        fora = c.execute(
            "SELECT api.votacao(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (2010, "presidente", "SP", None, False, 1, None, None, None, None, None, 5),
        ).fetchone()[0]
        print("2010", fora["status"])
        v26 = c.execute(
            "SELECT api.votacao(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (2026, "deputado_federal", "SP", None, False, 1, None, None, None, None, None, 5),
        ).fetchone()[0]
        print("2026 votacao", v26["status"])
        n = c.execute(
            "SELECT api.nominata(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (2022, "deputado_federal", None, None, "PL", None, None, None, 5),
        ).fetchone()[0]
        print("nominata PL", n["status"], len(n["linhas"]))
        v = c.execute(
            "SELECT api.votacao(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (2022, "presidente", "SP", None, False, 2, None, None, None, None, "validos", 5),
        ).fetchone()[0]
        print("pres SP t2", v["status"], [(x["nm_urna"], x["qt_votos"], x.get("pct")) for x in v.get("linhas", [])])
        vice = c.execute(
            "SELECT api.nominata(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (2022, "2", None, None, None, None, None, None, 3),
        ).fetchone()[0]
        print("vice cargo 2", vice["status"])


if __name__ == "__main__":
    main()
