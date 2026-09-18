#!/usr/bin/env python3
"""Auditoria adversarial em lote (item HARD-03-adversario-por-linha-em-lote).

Varre <laco>/handoffs atrás de laudo adversário por item e responde, sobre o estado.json:

  1. laudo por item: quais itens entregues/parciais têm laudo que os cita (e quais não têm);
  2. taxa de refutação: itens derrubados pelo adversário / itens que o adversário examinou
     (fonte: entradas do ledger cuja nota menciona adversário);
  3. lista de consertos: itens refutados pelo adversário e depois marcados entregue/parcial;
  4. portão: NENHUM item pode estar 'entregue' sem laudo — `--portao` sai 1 listando os
     faltosos. É o gancho para audita_ramo.sh / fila_merge.sh / driver.sh: rodar em lote
     depois de cada 20 itens juntados (o gatilho de cadência é do driver, não deste script).

O que conta como laudo (barra contra autorrelato e contra laudo vazio):
  - arquivo .md sob handoffs/ cujo NOME contém 'advers' ou 'refutacao' — o handoff do próprio
    construtor nunca entra (é o modo de falha apontado pelo laudo T9 linha-L7-2);
  - E o texto tem veredito (a palavra 'veredito' ou 'refutad*') E evidência de execução
    (bloco de código ```, seta de saída '->', ou as palavras evidência/saída/comando) — um
    arquivo com nome de laudo mas sem reprodução de comando NÃO conta (portão que só passa
    com fixture falsa);
  - E cita o id do item, no nome do arquivo ou no texto.

ponytail: a barra é heurística — pega laudo ausente, vazio ou autorrelato (o que derrubou o
item no T9), não prosa forjada com má-fé; essa continua sendo trabalho do adversário humano.

Uso:
  python3 adversario_lote.py [--laco CAMINHO] [--portao]
  python3 adversario_lote.py [--laco CAMINHO] --laudos-de <item>   # usado por marcar_item.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NOME_LAUDO = re.compile(r"advers|refutacao", re.I)
VEREDITO = re.compile(r"veredito|refutad", re.I)
EVIDENCIA = re.compile(r"```|\->|evid[êe]ncia|sa[íi]da|comando", re.I)
NOTA_ADVERSARIO = re.compile(r"^\s*(advers|adv\b)", re.I)  # entrada ASSINADA pelo adversário:
# "adversario G4: ...", "ADV G3: ..." — nota de construtor dizendo "sem adversario" não conta


def _laudos(laco: Path):
    """Percorre handoffs e devolve (caminho, texto) dos arquivos que passam na barra de laudo."""
    raiz = laco / "handoffs"
    if not raiz.is_dir():
        return
    for p in sorted(raiz.rglob("*.md")):
        if not NOME_LAUDO.search(p.name):
            continue
        try:
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if VEREDITO.search(texto) and EVIDENCIA.search(texto):
            yield p, texto


def itens_com_laudo(laco: Path | str, ids) -> dict[str, list[str]]:
    """{id do item: [laudos que o citam]} — só laudos que passam na barra."""
    laco = Path(laco)
    achados: dict[str, list[str]] = {}
    for p, texto in _laudos(laco):
        rel = str(p.relative_to(laco))
        for iid in ids:
            if iid in p.name or iid in texto:
                achados.setdefault(iid, []).append(rel)
    return achados


def auditar(laco: Path | str) -> dict:
    laco = Path(laco)
    estado = json.loads((laco / "estado.json").read_text(encoding="utf-8"))
    backlog = estado.get("backlog", [])
    entregues = [i["id"] for i in backlog if i.get("estado") == "entregue"]
    parciais = [i["id"] for i in backlog if i.get("estado") == "parcial"]
    com_laudo = itens_com_laudo(laco, entregues + parciais)
    sem_laudo = [i for i in entregues if i not in com_laudo]

    ledger = [ent for ent in estado.get("ledger", []) if isinstance(ent, dict)]
    adv = [ent for ent in ledger if NOTA_ADVERSARIO.search(str(ent.get("nota", "")))]
    auditados = {ent.get("item") for ent in adv if ent.get("item")}
    refutados = {ent.get("item") for ent in adv if ent.get("estado") == "refutado"}
    consertos = []
    for iid in sorted(refutados):
        caiu = False
        for ent in ledger:  # ledger é cronológico (append)
            if ent.get("item") != iid:
                continue
            if NOTA_ADVERSARIO.search(str(ent.get("nota", ""))) and ent.get("estado") == "refutado":
                caiu = True
            elif caiu and ent.get("estado") in ("entregue", "parcial"):
                consertos.append(iid)
                break
    sem_laudo_dono = [ent for ent in ledger
                      if ent.get("estado") == "entregue" and "SEM-LAUDO(dono)" in str(ent.get("nota", ""))]

    por_linha: dict[str, dict[str, int]] = {}
    for iid in entregues:
        m = re.match(r"(L\d+|HARD|D\d+)", iid)
        linha = m.group(1) if m else "?"
        d = por_linha.setdefault(linha, {"entregues": 0, "sem_laudo": 0})
        d["entregues"] += 1
        d["sem_laudo"] += iid in sem_laudo

    return {
        "entregues": entregues, "parciais": parciais, "com_laudo": com_laudo,
        "sem_laudo": sem_laudo, "auditados": sorted(auditados), "refutados": sorted(refutados),
        "consertos": consertos, "sem_laudo_dono": sem_laudo_dono, "por_linha": por_linha,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--laco", default=str(Path(__file__).resolve().parent),
                    help="raiz do laco (default: o diretório deste script)")
    ap.add_argument("--portao", action="store_true",
                    help="sai 1 se algum item entregue não tem laudo (gancho de auditoria)")
    ap.add_argument("--laudos-de", metavar="ITEM", help="só lista os laudos que citam ITEM")
    args = ap.parse_args()
    laco = Path(args.laco)

    if args.laudos_de:
        for rel in itens_com_laudo(laco, [args.laudos_de]).get(args.laudos_de, []):
            print(rel)
        return 0

    r = auditar(laco)
    n_ent = len(r["entregues"])
    print(f"itens entregues: {n_ent} · parciais: {len(r['parciais'])}")
    print(f"com laudo adversário: {n_ent - len(r['sem_laudo'])}/{n_ent} entregues")
    print("\npor linha (entregues / sem laudo):")
    for linha in sorted(r["por_linha"]):
        d = r["por_linha"][linha]
        print(f"  {linha:<6} {d['entregues']:>3} entregues · {d['sem_laudo']} sem laudo")
    n_adv = len(r["auditados"])
    taxa = f"{len(r['refutados'])}/{n_adv} ({100 * len(r['refutados']) / n_adv:.0f} %)" if n_adv else "—"
    print(f"\ntaxa de refutação: {taxa} dos itens examinados pelo adversário")
    print(f"lista de consertos ({len(r['consertos'])}): {', '.join(r['consertos']) or '—'}")
    if r["sem_laudo_dono"]:
        print("\nENTREGUE VIA OVERRIDE DO DONO (SEM-LAUDO(dono), auditar primeiro):")
        for ent in r["sem_laudo_dono"]:
            print(f"  {ent.get('item')} — {str(ent.get('nota', ''))[:140]}")
    if r["sem_laudo"]:
        print(f"\nENTREGUE SEM LAUDO ({len(r['sem_laudo'])}):")
        for iid in r["sem_laudo"]:
            print(f"  {iid}")
    if args.portao and r["sem_laudo"]:
        print("\nPORTÃO HARD-03 REPROVADO: item entregue sem laudo adversário.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
