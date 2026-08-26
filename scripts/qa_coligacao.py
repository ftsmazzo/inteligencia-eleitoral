import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tse_util import dsn
import psycopg

with psycopg.connect(dsn()) as c:
    print("by ano", c.execute("select ano, count(*) from eleicao.coligacao group by 1 order by 1").fetchall())
    print("BR pres 2022", c.execute("select count(*) from eleicao.coligacao where ano=2022 and sg_uf='BR'").fetchone())
    print("mun 2016", c.execute("select count(*) from eleicao.coligacao where ano=2016 and cd_municipio_tse>0").fetchone())
