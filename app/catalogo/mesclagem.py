"""Mesclagem de três vias por nó (item L5-13-edicao-concorrente; L5_CONCEITO D12: "mesclagem automática quando os
dois lados alteraram nós diferentes"). Entrada: o corpo BASE (a versão que o cliente leu, `base_versao`), o corpo
do SERVIDOR (o que está gravado agora) e o corpo do CLIENTE (o que ele quer gravar). Cada nó de `corpo.nos` é
identificado pelo `id` (ULID, estável entre versões — o editor nunca troca o id de um nó existente):

  - nó que só um lado mudou (alterou, criou ou removeu) fica como esse lado deixou;
  - nó que os dois lados mudaram de forma IGUAL fica igual;
  - nó que os dois lados mudaram de forma DIFERENTE (inclusive um removeu e o outro alterou) é CONFLITO —
    a função devolve a lista e quem chama responde 409 com o documento atual; nada é escolhido às escondidas.

`ligacoes` e as demais chaves de `corpo` (fora `nos`) seguem a mesma regra, cada ligação identificada pelo seu
JSON canônico (a lista é um conjunto) e cada chave de corpo como uma unidade.

Ordem dos nós no resultado: a ordem do CLIENTE para os nós que ele tem, com os nós que só o servidor criou (ou
que o cliente não conhecia) inseridos logo depois do nó que os antecede no servidor. Determinístico e sem tocar
o banco: função pura, testada com 100 pares de edições aleatórias em nós disjuntos (tests/unit/test_mesclagem.py)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any


def _canonico(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _por_id(nos: list) -> dict[str, dict]:
    saida: dict[str, dict] = {}
    for n in nos or []:
        if isinstance(n, dict) and isinstance(n.get("id"), str):
            saida[n["id"]] = n
    return saida


@dataclass
class Resultado:
    corpo: dict
    do_cliente: list[str] = field(default_factory=list)  # ids de nó que ficaram como o cliente deixou
    do_servidor: list[str] = field(default_factory=list)  # ids de nó que ficaram como o servidor deixou
    conflitos: list[dict] = field(default_factory=list)  # [{id, cliente, servidor}] — vazio = mesclou tudo
    chaves_conflito: list[str] = field(default_factory=list)  # chaves de corpo fora `nos` em conflito

    @property
    def ok(self) -> bool:
        return not self.conflitos and not self.chaves_conflito

    def relatorio(self) -> dict:
        return {
            "do_cliente": self.do_cliente, "do_servidor": self.do_servidor,
            "conflitos": [c["id"] for c in self.conflitos], "chaves_conflito": self.chaves_conflito,
        }


def _tres_vias(base: Any, servidor: Any, cliente: Any) -> tuple[str, Any]:
    """Uma unidade (nó, ligação ou chave): devolve ('base'|'cliente'|'servidor'|'igual'|'conflito', valor)."""
    sb, ss, sc = _canonico(base), _canonico(servidor), _canonico(cliente)
    mudou_s, mudou_c = ss != sb, sc != sb
    if not mudou_s and not mudou_c:
        return "base", base
    if mudou_c and not mudou_s:
        return "cliente", cliente
    if mudou_s and not mudou_c:
        return "servidor", servidor
    if ss == sc:
        return "igual", cliente
    return "conflito", None


def mesclar(base: dict | None, servidor: dict | None, cliente: dict | None) -> Resultado:
    base, servidor, cliente = base or {}, servidor or {}, cliente or {}
    nb, ns, nc = _por_id(base.get("nos")), _por_id(servidor.get("nos")), _por_id(cliente.get("nos"))
    res = Resultado(corpo={})
    decidido: dict[str, dict | None] = {}  # id -> nó final (None = removido)
    for nid in sorted(set(nb) | set(ns) | set(nc)):
        origem, valor = _tres_vias(nb.get(nid), ns.get(nid), nc.get(nid))
        if origem == "conflito":
            res.conflitos.append({"id": nid, "cliente": nc.get(nid), "servidor": ns.get(nid)})
            continue
        if origem == "cliente":
            res.do_cliente.append(nid)
        elif origem == "servidor":
            res.do_servidor.append(nid)
        decidido[nid] = copy.deepcopy(valor)
    # ordem: a do cliente; nós que só o servidor tem entram depois do seu antecessor no servidor
    nos_cliente = cliente.get("nos") or []
    ordem: list[str] = [n["id"] for n in nos_cliente if isinstance(n, dict) and n.get("id") in decidido]
    vistos = set(ordem)
    nos_servidor = servidor.get("nos") or []
    ordem_servidor = [n["id"] for n in nos_servidor if isinstance(n, dict) and isinstance(n.get("id"), str)]
    for i, nid in enumerate(ordem_servidor):
        if nid in vistos or nid not in decidido:
            continue
        antecessor = next((a for a in reversed(ordem_servidor[:i]) if a in vistos), None)
        pos = ordem.index(antecessor) + 1 if antecessor is not None else 0
        ordem.insert(pos, nid)
        vistos.add(nid)
    res.corpo["nos"] = [decidido[nid] for nid in ordem if decidido.get(nid) is not None]

    # ligações: conjunto por JSON canônico
    lb = {_canonico(x): x for x in base.get("ligacoes") or []}
    ls = {_canonico(x): x for x in servidor.get("ligacoes") or []}
    lc = {_canonico(x): x for x in cliente.get("ligacoes") or []}
    ligacoes: list = []
    for chave in list(dict.fromkeys([*lc, *ls, *lb])):
        origem, valor = _tres_vias(lb.get(chave), ls.get(chave), lc.get(chave))
        if origem == "conflito":  # impossível para conjunto (presença/ausência iguais ou não); fica por segurança
            res.chaves_conflito.append("ligacoes")
            continue
        if valor is not None:
            ligacoes.append(copy.deepcopy(valor))
    res.corpo["ligacoes"] = ligacoes

    # demais chaves do corpo, cada uma como unidade
    for chave in sorted((set(base) | set(servidor) | set(cliente)) - {"nos", "ligacoes"}):
        origem, valor = _tres_vias(base.get(chave), servidor.get(chave), cliente.get(chave))
        if origem == "conflito":
            res.chaves_conflito.append(chave)
            continue
        lado = cliente if origem == "cliente" else servidor if origem == "servidor" else base
        if chave not in lado:
            continue  # o lado que decidiu removeu a chave
        res.corpo[chave] = copy.deepcopy(valor)
    return res
