#!/usr/bin/env python3
"""Fila de varredura do adversário: itens entregues ou parciais que NUNCA foram atacados,
em ordem de RISCO, não de id. Derivado do estado real + dos laudos em disco.

Uso: python3 sem_adversario.py            # a fila
     python3 sem_adversario.py --linha    # agrupado por linha (para atacar irmãos de uma vez)
"""
import json, glob, os, re, sys

B = "/home/dev/plataforma/laco"
e = json.load(open(f"{B}/estado.json"))
itens = {x["id"]: x for x in e["backlog"]}
alvo = [x for x in e["backlog"] if x["estado"] in ("entregue", "parcial")]

# 1. quem JÁ tem laudo: nome do arquivo, texto do laudo, ou veredito no ledger
atacados = set()
for f in glob.glob(f"{B}/handoffs/*/*ADVERS*") + glob.glob(f"{B}/handoffs/*/*/50_*"):
    txt = ""
    try:
        txt = open(f, encoding="utf-8", errors="ignore").read()[:6000]
    except OSError:
        pass
    for i in itens:
        if i in os.path.basename(f) or i in txt[:2000]:
            atacados.add(i)
for l in e.get("ledger", []):
    if isinstance(l, dict) and re.search(r"advers", str(l.get("nota", "")), re.I):
        atacados.add(l.get("item"))

# 2. risco: o que dói se estiver errado
RISCO = [
    (1, "identidade, sessão, segundo fator, senha", r"auth|login|senha|2fa|totp|sessao|sessão|token|ldap|usuario|usuário|papel|privilegio|privilégio|perfil"),
    (2, "isolamento entre inquilinos", r"tenant|inquilino|rls|cruzad|svc|escopo|compartilha"),
    (3, "dado de cliente e arquivo enviado", r"arquivo|objeto|upload|ingest|garage|anexo|raster|import"),
    (4, "fila de trabalhos e catálogo", r"job|tarefa|fila|worker|catalogo|catálogo|item|busca|versao|versão"),
    (5, "resto", r"."),
]

def risco(x):
    alvo_txt = f"{x['id']} {x.get('hipotese','')} {x.get('portao_de_pronto','')}".lower()
    for n, nome, pad in RISCO:
        if re.search(pad, alvo_txt):
            return n, nome
    return 5, "resto"

fila = []
for x in alvo:
    if x["id"] in atacados:
        continue
    n, nome = risco(x)
    fila.append((n, nome, x))
fila.sort(key=lambda t: (t[0], t[2]["id"]))

print(f"itens entregues ou parciais: {len(alvo)}")
print(f"com laudo de adversário: {len(atacados & {x['id'] for x in alvo})}  ->  {sorted(atacados & {x['id'] for x in alvo})}")
print(f"NUNCA ATACADOS: {len(fila)}\n")

if "--linha" in sys.argv:
    porlinha = {}
    for n, nome, x in fila:
        porlinha.setdefault((n, nome, x["linha"]), []).append(x["id"])
    for (n, nome, linha), ids in sorted(porlinha.items()):
        print(f"risco {n} · {nome} · {linha}  ({len(ids)} itens)")
        print("   " + "  ".join(ids))
        print()
else:
    atual = None
    for n, nome, x in fila:
        if n != atual:
            print(f"\n--- RISCO {n}: {nome}")
            atual = n
        print(f"  {x['estado']:8} {x['id']:52} {x['linha']}")
