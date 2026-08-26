import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import ROOT, dsn
import psycopg

sql = (ROOT / "sql" / "patch_candidato_complementar.sql").read_text(encoding="utf-8")
with psycopg.connect(dsn(), autocommit=True) as c:
    c.execute(sql)
    print(
        "ok",
        c.execute(
            "select to_regclass('eleicao.rede_social'), to_regclass('eleicao.bem')"
        ).fetchone(),
    )
