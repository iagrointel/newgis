"""Ataque adversarial G3 ao item L0-05-a-fila-postgres — refutação LITERAL:
"adversário mata o worker com SIGKILL (não SIGTERM) 3 vezes seguidas no mesmo job e verifica que o job
termina 'falhou' na 4ª e nunca 'concluido'".

Roteiro autônomo (não é pytest: precisa ser o ÚNICO worker da base). Uso:
  set -a; source /home/dev/plataforma/laco/var/trilha/adv3.env; set +a
  venv/bin/python tests/api/adversario_g3/g3_sigkill_worker.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

ESQUEMA = os.environ.get("PLAT_SCHEMA", "plat")
LIMITE_SEM_SINAL_S = 60


def sql(consulta: str) -> list[dict]:
    """Roda como superusuário (plat_app/plat_worker não têm DELETE/INSERT direto em plat.job: é de propósito)."""
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-A", "-t",
                        "-v", "ON_ERROR_STOP=1", "-c",
                        f"SET search_path = {ESQUEMA}, public; " + consulta],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    ruido = ("SET", "BEGIN", "COMMIT", "ROLLBACK")
    return [l for l in r.stdout.splitlines() if l.strip() and not l.split()[0] in ruido
            and not l.split()[0] in ("INSERT", "UPDATE", "DELETE", "SELECT")]


def sobe_worker(porta: int) -> subprocess.Popen:
    amb = dict(os.environ, PLAT_WORKER_NOME=f"advkill{porta}", PLAT_WORKER_PROCESSOS="1",
               PLAT_WORKER_URL=f"http://127.0.0.1:{porta}", PYTHONNOUSERSITE="1")
    p = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], env=amb,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
    return p


def estado(jid):
    linha = sql(f"SELECT estado || '|' || tentativa || '|' || reinicios || '|' || coalesce(worker,'') "
                f"|| '|' || coalesce(left(erro,80),'') FROM job WHERE id = '{jid}'")[0]
    e, t, rr, w, err = linha.split("|", 4)
    return {"estado": e, "tentativa": int(t), "reinicios": int(rr), "worker": w, "erro": err}


def main():
    sql("DELETE FROM job WHERE parametros->>'marcador_adv3' IS NOT NULL")
    jid = sql("""INSERT INTO job(tenant_id, usuario_id, tipo, parametros, pesado, memoria_mb, timeout_s,
                                 max_tentativas)
                 SELECT t.id, NULL, 'prova.progresso',
                        '{"duracao_s": 45, "passos": 45, "marcador_adv3": "sigkill"}'::jsonb,
                        false, 256, 600, 3 FROM tenant t WHERE t.slug = 'demo' RETURNING id""")[0]
    trilha = [{"passo": "job criado", **estado(jid)}]
    for ciclo in (1, 2, 3):
        w = sobe_worker(18170 + ciclo)
        for _ in range(120):
            if estado(jid)["estado"] == "rodando":
                break
            time.sleep(0.5)
        else:
            trilha.append({"passo": f"ciclo {ciclo}: o worker NUNCA pegou o job", **estado(jid)})
            break
        time.sleep(4)
        os.kill(w.pid, signal.SIGKILL)
        w.wait()
        trilha.append({"passo": f"ciclo {ciclo}: SIGKILL no worker", **estado(jid)})
        # sem worker vivo, ninguém ceifa: mede quanto tempo o job fica 'rodando' sozinho
        time.sleep(LIMITE_SEM_SINAL_S + 8)
        trilha.append({"passo": f"ciclo {ciclo}: {LIMITE_SEM_SINAL_S + 8} s depois, SEM worker vivo",
                       **estado(jid)})
    # 4ª passagem: sobe worker e deixa terminar
    w = sobe_worker(18179)
    fim = time.monotonic() + 180
    while time.monotonic() < fim:
        e = estado(jid)
        if e["estado"] in ("concluido", "falhou", "cancelado"):
            break
        time.sleep(1)
    trilha.append({"passo": "4a passagem, worker vivo", **estado(jid)})
    os.kill(w.pid, signal.SIGTERM)
    try:
        w.wait(timeout=40)
    except subprocess.TimeoutExpired:
        os.kill(w.pid, signal.SIGKILL)
    final = estado(jid)
    veredito = ("PASSA" if final["estado"] == "falhou" else
                f"CAI: a refutação exige 'falhou' na 4ª e NUNCA 'concluido'; deu '{final['estado']}'")
    print(json.dumps({"job": str(jid), "trilha": trilha, "final": final, "veredito": veredito},
                     ensure_ascii=False, indent=2, default=str))
    sql(f"DELETE FROM job WHERE id = '{jid}'")


if __name__ == "__main__":
    main()
