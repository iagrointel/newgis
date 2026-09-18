"""Mesclagem de três vias por nó (item L5-13-edicao-concorrente; L5_CONCEITO D12: "mesclagem automática quando os
dois lados alteraram nós diferentes"). Entrada: o corpo BASE (a versão que o cliente leu, `base_versao`), o corpo
do SERVIDOR (o que está gravado agora) e o corpo do CLIENTE (o que ele quer gravar). Cada nó de `corpo.nos` é
identificado pelo `id` (ULID, estável entre versões — o editor nunca troca o id de um nó existente):

  - nó que só um lado mudou (alterou, criou ou removeu) fica como esse lado deixou;
  - nó que os dois lados mudaram de forma IGUAL fica igual;
  - nó que os dois lados mudaram de forma DIFERENTE (inclusive um removeu e o outro alterou) é CONFLITO —
    a função devolve a lista e quem chama responde 409 com o documento atual; nada é escolhido às escondidas.

`ligacoes` e as demais chaves de `corpo` (fora `nos`) seguem a mesma regra. Uma ligação não tem id próprio:
ela é identificada pelo PAR (`de`, `para`), que é a identidade lógica dela no documento — assim, dois lados
que mudam um campo da mesma ligação (o `tipo`, por exemplo) caem na mesma unidade e viram CONFLITO, como
qualquer nó mudado dos dois lados. Quando o mesmo par aparece duas vezes num dos lados (o documento admite
duas ligações distintas entre os mesmos nós), essas voltam a ser identificadas pelo JSON canônico, e aí a
lista é um conjunto. Cada chave de corpo fora `nos`/`ligacoes` é uma unidade.

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


def _chave_par(x: Any):
    """Identidade lógica de uma ligação: o par (de, para). `None` quando o objeto não tem os dois."""
    if isinstance(x, dict) and isinstance(x.get("de"), str) and isinstance(x.get("para"), str):
        return (x["de"], x["para"])
    return None


def _mapas_de_ligacoes(base, servidor, cliente) -> tuple[dict, dict, dict]:
    """Os três lados indexados pela MESMA chave. Sem id próprio, uma ligação é reconhecida pelo par
    (de, para): é isso que faz "os dois lados mudaram o `tipo` da mesma ligação" virar uma unidade só, que
    `_tres_vias` consegue chamar de conflito, em vez de duas adições independentes que sobrevivem juntas.

    Quando o mesmo par aparece mais de uma vez em QUALQUER dos três lados (o documento admite duas ligações
    distintas entre os mesmos dois nós), o par deixa de ser identidade e essas ligações voltam à chave
    canônica do objeto inteiro — o comportamento antigo, de conjunto, que para esse caso é o correto."""
    listas = [list(base or []), list(servidor or []), list(cliente or [])]
    repetidos: set = set()
    for lista in listas:
        vistos: set = set()
        for x in lista:
            par = _chave_par(x)
            if par is None:
                continue
            if par in vistos:
                repetidos.add(par)
            vistos.add(par)

    def mapa(lista: list) -> dict:
        saida: dict = {}
        for x in lista:
            par = _chave_par(x)
            chave = ("par", par) if (par is not None and par not in repetidos) else ("canonico", _canonico(x))
            saida[chave] = x
        return saida

    return mapa(listas[0]), mapa(listas[1]), mapa(listas[2])


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

    # ligações: identidade LÓGICA pelo par (de, para) quando ele existe e é único nos três lados; só quando
    # não dá é que se cai no JSON canônico do objeto inteiro (ver `_mapas_de_ligacoes`).
    lb, ls, lc = _mapas_de_ligacoes(base.get("ligacoes"), servidor.get("ligacoes"), cliente.get("ligacoes"))
    ligacoes: list = []
    for chave in list(dict.fromkeys([*lc, *ls, *lb])):
        origem, valor = _tres_vias(lb.get(chave), ls.get(chave), lc.get(chave))
        if origem == "conflito":
            # os dois lados mudaram a MESMA ligação lógica de formas diferentes: quem chama responde 409 com
            # o documento atual. O corpo devolvido fica com a ligação como o SERVIDOR a tem — nunca com as
            # duas variantes contraditórias lado a lado, que era o que acontecia com a chave canônica.
            res.chaves_conflito.append("ligacoes")
            if ls.get(chave) is not None:
                ligacoes.append(copy.deepcopy(ls[chave]))
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
