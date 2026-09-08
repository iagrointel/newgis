#!/usr/bin/env python3
"""DIARIO.md — o log corrido do laço, em linguagem de gente, gerado do que existe:
git (commits com data), estado.json (ledger, placar, decisões), tests/medidas/*.json (números),
handoffs (papéis que rodaram) e refutacao.json (vereditos). Rodar a cada turno (cronista)."""
import json, subprocess, pathlib, datetime, re

B = pathlib.Path("/home/dev/plataforma/laco")
R = pathlib.Path("/home/dev/plataforma/enterprise")
e = json.loads((B / "estado.json").read_text())

def git(*a):
    return subprocess.run(["git", "-C", str(R), *a], capture_output=True, text=True).stdout.strip()

commits = [l.split("\x1f") for l in git("log", "--pretty=%h\x1f%ad\x1f%s", "--date=format:%d/%m %H:%M").split("\n") if l]
medidas = {}
for f in sorted((R / "tests" / "medidas").glob("*.json")):
    try:
        medidas[f.stem] = json.loads(f.read_text()).get("medidas", {})
    except Exception:
        pass

L = []
L.append("# DIÁRIO DO LAÇO — plataforma (codinome plat)\n")
L.append(f"Gerado por `laco/gera_diario.py` em {datetime.datetime.now():%d/%m/%Y %H:%M}. "
         "Fonte: git, `estado.json`, `tests/medidas/*.json`, handoffs. Não editar à mão.\n")

pl = e["placar"]
L.append(f"**Placar:** {pl['entregues']} entregue(s) · {pl.get('parciais',0)} parcial(is) · "
         f"{pl.get('refutados',0)} refutado(s) · {pl['total']} itens no total · turno {e['turno']} · "
         f"{len(commits)} commits.\n")

L.append("## Linha do tempo (do mais recente para o mais antigo)\n")
dia = None
for h, d, s in commits:
    if d.split()[0] != dia:
        dia = d.split()[0]
        L.append(f"\n### {dia}\n")
    L.append(f"- `{h}` {d.split()[1]} — {s}")

L.append("\n## Registro por item (ledger)\n")
for r in e["ledger"]:
    if "construido" in r:
        L.append(f"\n### Turno {r['turno']} · {r['item']} · {r['quando']}")
        L.append(f"- **Construído:** {r['construido']}")
        if r.get("medicoes"):
            m = r["medicoes"]
            L.append("- **Medições:** " + (m if isinstance(m, str) else " · ".join(f"{k} {v}" for k, v in m.items())))
        if r.get("adversario"):
            L.append(f"- **Adversário:** {r['adversario']}")
        if r.get("portao"):
            L.append(f"- **Portão:** {r['portao']}")
        if r.get("proximo_passo"):
            L.append(f"- **Próximo passo:** {r['proximo_passo']}")
    else:
        L.append(f"- Turno {r.get('turno')} · {r.get('quando')} · {r.get('item','')}: {r.get('evento','')}")

L.append("\n## Vereditos dos adversários\n")
for f in sorted(B.glob("handoffs/*/*/refutacao.json")) + sorted(B.glob("handoffs/*/refutacao.json")):
    try:
        d = json.loads(f.read_text())
        L.append(f"- **{d.get('item', f.parent.name)}**: {d.get('veredito')} "
                 f"({len(d.get('evidencia', []))} ataques registrados) — `{f.relative_to(B)}`")
    except Exception:
        pass

L.append("\n## Números medidos (tests/medidas)\n")
for item, m in medidas.items():
    if not m:
        continue
    L.append(f"\n### {item}")
    for k, v in m.items():
        val = v.get("valor") if isinstance(v, dict) else v
        un = v.get("unidade", "") if isinstance(v, dict) else ""
        L.append(f"- {k}: **{val}** {un}".rstrip())

L.append("\n## Decisões do dono em aberto\n")
for d in e["decisoes_do_dono"]:
    if "aberta" in str(d.get("estado", "")).lower() or "adiada" in str(d.get("estado", "")).lower():
        L.append(f"- **{d['id']}** — {d['pergunta']}")

L.append("\n## Notas do laço\n")
for n in e.get("notas", []):
    L.append(f"- {n}")

(B / "DIARIO.md").write_text("\n".join(L) + "\n")
print(f"{B/'DIARIO.md'}: {len(L)} linhas · {len(commits)} commits · {len(medidas)} arquivos de medida")
