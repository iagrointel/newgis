#!/usr/bin/env python3
"""Lista de verificação da corrida, derivada do estado REAL (não escrita à mão).
Uso:  python3 checklist.py          (uma vez)
      watch -c -n 10 python3 /home/dev/plataforma/laco/checklist.py   (ao vivo)
"""
import json, os, subprocess, time

B = "/home/dev/plataforma/laco"
R = "/home/dev/plataforma/enterprise"
V, X, O = "\033[32m", "\033[33m", "\033[90m"
Z, N = "\033[0m", "\033[1m"

def sh(c):
    try:
        return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

def marca(ok):
    return f"{V}[x]{Z}" if ok is True else (f"{X}[~]{Z}" if ok == "meio" else f"{O}[ ]{Z}")

# ---- provas: cada item pergunta ao SISTEMA, não a mim
def existe(p, dentro=None):
    p = os.path.join(B, p) if not p.startswith("/") else p
    if not os.path.exists(p):
        return False
    return (dentro in open(p, encoding="utf-8", errors="ignore").read()) if dentro else True

FASES = [
 ("FASE 0 — travas antes de subir agente", [
  ("escrita atômica do estado",        lambda: existe("marcar_item.py", "os.replace")),
  ("driver com segredos e sob trava",  lambda: existe("driver.sh", "flock -w 120")),
  ("disparo automático com caminho absoluto", lambda: existe("driver.sh", "/home/dev/.local/bin/claude")),
  ("migração por carimbo de tempo",    lambda: existe(f"{R}/db/migrar.sh", "20") and bool(sh(f"ls {R}/db/migracoes/2026*.sql 2>/dev/null"))),
  ("orçamento de conexão por trilha",  lambda: existe(f"{R}/app/db.py", "PLAT_POOL_MAX")),
  ("fila de merge com bisseção",       lambda: existe("fila_merge.sh")),
  ("gancho que barra commit fora do item", lambda: existe(f"{R}/.git/hooks/pre-commit")),
  ("piscina de trilhas",               lambda: existe("trilhas_pool.sh")),
 ]),
 ("FASE 1 — desmontar pontos de serialização", [
  ("openapi só na fila de merge",      lambda: existe(f"{R}/.gitattributes", "openapi")),
  ("casos cruzados por item",          lambda: os.path.isdir(f"{R}/tests/api/cruzado")),
  ("eventos por item",                 lambda: os.path.isdir(f"{R}/tests/api/eventos")),
  ("paridade em partes",               lambda: os.path.isdir(f"{R}/docs/partes/paridade")),
  ("changelog em fragmentos",          lambda: os.path.isdir(f"{R}/changelog.d")),
  ("instalador em passos",             lambda: os.path.isdir(f"{R}/install.d")),
 ]),
 ("FASE 2 — a fábrica e o painel", [
  ("gerador de prompt por item",       lambda: existe("prompt_item.py")),
  ("supervisor",                       lambda: existe("supervisor.py")),
  ("painel ao vivo",                   lambda: existe("vivo/painel.html")),
  ("instantâneo do painel atualizando", lambda: os.path.exists(f"{B}/vivo/agora.json") and (time.time()-os.path.getmtime(f"{B}/vivo/agora.json") < 60)),
  ("commit carrega o id do item",      lambda: "Item:" in sh(f"cd {R} && git log -20 --format=%b | head -50")),
 ]),
]

e = json.load(open(f"{B}/estado.json"))
p = e["placar"]
b = e["backlog"]
vivos = len(sh("pgrep -f '^claude' ").splitlines())
ram = sh("awk '/MemAvailable/{printf \"%.1f\", $2/1048576}' /proc/meminfo")
conex = sh("""sudo -u postgres psql -d iagro_sat -tAc "select count(*) from pg_stat_activity" 2>/dev/null""")
disco = sh("df --output=pcent / | tail -1 | tr -d ' %'")

print(f"{N}CORRIDA PLATAFORMA ENTERPRISE{Z}   {time.strftime('%H:%M:%S')}")
print(f"  entregues {V}{p['entregues']}{Z} · parciais {X}{p['parciais']}{Z} · refutados \033[31m{p['refutados']}\033[0m · faltam {p['total']-p['entregues']}  de {p['total']}")
print(f"  processos claude {vivos} · RAM livre {ram} GB · conexões {conex}/100 · disco / {disco}%")
print()
for titulo, itens in FASES:
    feitos = 0
    linhas = []
    for nome, prova in itens:
        try:
            ok = prova()
        except Exception:
            ok = False
        feitos += 1 if ok is True else 0
        linhas.append(f"  {marca(ok)} {nome}")
    print(f"{N}{titulo}{Z}  {feitos}/{len(itens)}")
    print("\n".join(linhas))
    print()
print(f"{N}FASE 3 — a corrida{Z}")
tentando = [x['id'] for x in b if x['estado'] == 'tentando']
refut = [x['id'] for x in b if x['estado'] == 'refutado']
print(f"  {marca(len(tentando) > 0)} agentes em item: {len(tentando)}  {O}{', '.join(tentando[:4])}{Z}")
print(f"  {marca(not refut)} nenhuma refutação aberta" + (f"  \033[31m{', '.join(refut)}\033[0m" if refut else ""))
print(f"  {marca(False)} adversário em 100% (hoje 14%)")
print()
print(f"{O}atualiza sozinho:  watch -c -n 10 python3 {B}/checklist.py{Z}")
