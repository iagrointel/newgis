import asyncio, json, time, statistics, sys, httpx, psycopg2, psycopg2.extensions
from dotenv import dotenv_values
dsn = dotenv_values('/home/dev/plataforma/enterprise/.env')['PLAT_DSN']
N_CLIENTES = int(sys.argv[1]); N_EVENTOS = int(sys.argv[2])
async def cliente(jid, lat):
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("GET", f"http://127.0.0.1:18159/api/jobs/{jid}/eventos") as r:
            async for linha in r.aiter_lines():
                if linha.startswith("data: "):
                    d = json.loads(linha[6:]); lat.append(time.time() - d["t"])
                    if d.get("estado") == "concluido": return
async def main():
    lat = []
    tarefas = [asyncio.create_task(cliente("j1", lat)) for _ in range(N_CLIENTES)]
    await asyncio.sleep(1.0)
    con = psycopg2.connect(dsn); con.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()
    for i in range(N_EVENTOS):
        est = "concluido" if i == N_EVENTOS - 1 else "rodando"
        cur.execute("SELECT pg_notify('plat_job', %s)", (json.dumps({"job": "j1", "progresso": i, "estado": est, "t": time.time()}),))
        await asyncio.sleep(0.2)
    await asyncio.gather(*tarefas)
    print(f"clientes={N_CLIENTES} eventos={N_EVENTOS} entregas={len(lat)} latencia_ms mediana={statistics.median(lat)*1000:.2f} p95={sorted(lat)[int(len(lat)*0.95)]*1000:.2f} max={max(lat)*1000:.2f}")
asyncio.run(main())
