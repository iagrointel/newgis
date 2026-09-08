"""Mede: (1) latência LISTEN/NOTIFY entre duas conexões plat_app; (2) SELECT ... FOR UPDATE SKIP LOCKED em tabela
temporária com 10.000 linhas, 200 fetches; (3) tamanho máximo de payload de NOTIFY (8000 bytes documentado)."""
import os, select, time, statistics, psycopg2, psycopg2.extensions
from dotenv import dotenv_values
dsn = dotenv_values('.env')['PLAT_DSN']
a = psycopg2.connect(dsn); a.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
b = psycopg2.connect(dsn); b.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
ca = a.cursor(); ca.execute("LISTEN plat_job_med")
lat = []
for i in range(200):
    t0 = time.perf_counter()
    b.cursor().execute("SELECT pg_notify('plat_job_med', %s)", (f'{{"i":{i}}}',))
    while True:
        if select.select([a], [], [], 2) == ([], [], []): raise SystemExit("timeout notify")
        a.poll()
        if a.notifies:
            a.notifies.clear(); break
    lat.append((time.perf_counter() - t0) * 1000)
print(f"notify_latencia_ms mediana={statistics.median(lat):.3f} p95={sorted(lat)[int(len(lat)*0.95)]:.3f} max={max(lat):.3f} n={len(lat)}")
# payload 8000
try:
    b.cursor().execute("SELECT pg_notify('plat_job_med', repeat('x', 7999))"); print("notify_payload_7999=ok")
    b.cursor().execute("SELECT pg_notify('plat_job_med', repeat('x', 8001))"); print("notify_payload_8001=ok")
except Exception as e:
    print("notify_payload_8001=erro:", str(e).strip().splitlines()[0])
# SKIP LOCKED
c = psycopg2.connect(dsn); cc = c.cursor()
cc.execute("CREATE TEMP TABLE fila(id bigserial primary key, estado text not null default 'pendente', prioridade int not null default 5, criado_em timestamptz default clock_timestamp())")
cc.execute("INSERT INTO fila(prioridade) SELECT (random()*9)::int FROM generate_series(1,10000)")
cc.execute("CREATE INDEX ON fila(prioridade, criado_em) WHERE estado='pendente'")
c.commit()
tf = []
for i in range(200):
    t0 = time.perf_counter()
    cc.execute("""WITH j AS (SELECT id FROM fila WHERE estado='pendente' ORDER BY prioridade, criado_em
                  FOR UPDATE SKIP LOCKED LIMIT 1)
                  UPDATE fila f SET estado='rodando' FROM j WHERE f.id=j.id RETURNING f.id""")
    cc.fetchone(); c.commit()
    tf.append((time.perf_counter() - t0) * 1000)
print(f"skip_locked_fetch_ms mediana={statistics.median(tf):.3f} p95={sorted(tf)[int(len(tf)*0.95)]:.3f} n={len(tf)} linhas=10000")
