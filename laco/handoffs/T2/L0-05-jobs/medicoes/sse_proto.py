"""Protótipo de SSE: um thread LISTEN por processo alimenta filas asyncio por job (fan-out); rota async não
segura token do threadpool. Porta de rascunho 18159 (fora da faixa 8150-8159)."""
import asyncio, json, select, threading, psycopg2, psycopg2.extensions
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from dotenv import dotenv_values
dsn = dotenv_values('/home/dev/plataforma/enterprise/.env')['PLAT_DSN']
app = FastAPI()
assinantes: dict[str, set[asyncio.Queue]] = {}
loop_ref = {}

def escutar():
    con = psycopg2.connect(dsn); con.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor(); cur.execute("LISTEN plat_job")
    while True:
        if select.select([con], [], [], 5) == ([], [], []): continue
        con.poll()
        while con.notifies:
            n = con.notifies.pop(0)
            try: dados = json.loads(n.payload)
            except Exception: continue
            for q in list(assinantes.get(dados.get("job"), ())):
                loop_ref["loop"].call_soon_threadsafe(q.put_nowait, dados)

@app.on_event("startup")
async def inicio():
    loop_ref["loop"] = asyncio.get_running_loop()
    threading.Thread(target=escutar, daemon=True).start()

@app.get("/api/jobs/{jid}/eventos")
async def eventos(jid: str):
    q: asyncio.Queue = asyncio.Queue()
    assinantes.setdefault(jid, set()).add(q)
    async def gen():
        try:
            yield ": ok\n\n"
            while True:
                try:
                    d = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: progresso\ndata: {json.dumps(d)}\n\n"
                    if d.get("estado") in ("concluido", "falhou", "cancelado"): break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            assinantes[jid].discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
