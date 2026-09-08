"""Motor de formulário no servidor (item L2-07-b): relevância, cálculo e restrição sobre o mesmo AST que o
navegador avalia (`web/js/coleta/motor.js`). O servidor nunca confia no navegador: recalcula, reavalia relevância
(campo não relevante vira nulo) e reaplica restrições e obrigatoriedade antes de gravar. Erros voltam por
campo, com a mensagem de restrição no idioma padrão do formulário; nada é gravado com erro (refutação)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.coleta.documento import contexto_de, folhas, nos, valor_para_contexto
from app.expressao.avaliador_py import ErroExpressao, ast_de_json, avaliar


@dataclass
class Resultado:
    valores: dict[str, Any]
    repeticoes: dict[str, list[dict]]
    relevantes: set[str] = field(default_factory=set)
    erros: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros


def _avaliar(regra: dict | None, ctx: dict) -> tuple[Any, str | None]:
    """(valor, erro). Regra ausente = (None, None). Erro de avaliação nunca derruba a resposta inteira: vira
    erro nomeado do campo."""
    if not regra or not regra.get("ast"):
        return None, None
    try:
        return avaliar(ast_de_json(regra["ast"]), ctx), None
    except ErroExpressao as e:
        return None, e.codigo


def _verdadeiro(valor: Any) -> bool:
    return bool(valor) and valor is not None


def opcoes(campo: dict, listas: dict, ctx: dict) -> list[dict]:
    """Linhas da lista do campo depois do `choice_filter` (cascata): a regra é avaliada por linha com `$_linha`."""
    linhas = listas.get(campo.get("lista") or "", [])
    filtro = campo.get("filtro_lista")
    if not filtro:
        return list(linhas)
    saida = []
    for linha in linhas:
        v, _erro = _avaliar(filtro, ctx | {"_linha": linha})
        if _verdadeiro(v):
            saida.append(linha)
    return saida


def _mensagem(campo: dict, doc: dict) -> str:
    msg = (campo.get("restricao") or {}).get("mensagem") or {}
    if isinstance(msg, str):
        return msg
    return msg.get(doc.get("idioma_padrao") or "") or next(iter(msg.values()), "") or "valor fora da regra"


def _calcular(doc: dict, valores: dict, repeticoes: dict) -> None:
    """Cálculos na ordem topológica; os de dentro de repetição rodam por linha (contexto raiz + linha)."""
    por_nome = {c["nome"]: (c, rep) for c, rep in folhas(doc["campos"])}
    for nome in doc.get("ordem_calculo") or []:
        if nome not in por_nome:
            continue
        campo, rep = por_nome[nome]
        if rep is None:
            ctx = contexto_de(doc, valores, repeticoes)
            v, _erro = _avaliar(campo["calculo"], ctx)
            valores[nome] = v
        else:
            for linha in repeticoes.get(rep) or []:
                ctx = contexto_de(doc, valores, repeticoes)
                ctx.update({k: valor_para_contexto(por_nome[k][0], v) for k, v in linha.items() if k in por_nome})
                v, _erro = _avaliar(campo["calculo"], ctx)
                linha[nome] = v


def _validar_no(no: dict, doc: dict, valores: dict, ctx: dict, res: Resultado, relevante_pai: bool,
                indice: int | None = None, rep: str | None = None) -> None:
    rel = relevante_pai
    if rel and no.get("relevante"):
        v, erro = _avaliar(no["relevante"], ctx)
        rel = _verdadeiro(v) and erro is None
    if no.get("tipo") in ("grupo", "repeticao"):
        if no["tipo"] == "repeticao":
            if not rel:
                res.repeticoes[no["nome"]] = []
                return
            res.relevantes.add(no["nome"])
            for i, linha in enumerate(res.repeticoes.get(no["nome"]) or []):
                ctx_linha = ctx | {k: valor_para_contexto(_por_nome(doc)[k], v) for k, v in linha.items()
                                   if k in _por_nome(doc)}
                for filho in no.get("filhos") or []:
                    _validar_no(filho, doc, linha, ctx_linha, res, True, i, no["nome"])
            return
        for filho in no.get("filhos") or []:
            _validar_no(filho, doc, valores, ctx, res, rel, indice, rep)
        return
    nome = no["nome"]
    if not rel:
        valores[nome] = None
        return
    res.relevantes.add(nome)
    valor = valores.get(nome)
    if valor == "":
        valor = None
        valores[nome] = None
    if no.get("tipo") in ("nota", "calculo", "meta"):
        return
    onde = {"campo": nome} | ({"repeticao": rep, "indice": indice} if rep else {})
    if no.get("obrigatorio") and valor is None:
        res.erros.append(onde | {"erro": "campo_obrigatorio", "mensagem": "campo obrigatório"})
        return
    if valor is None:
        return
    if no.get("tipo") in ("select_one", "select_multiple") and no.get("lista"):
        permitidas = {str(o["nome"]) for o in opcoes(no, doc.get("listas") or {}, ctx)}
        escolhidos = str(valor).split(" ") if no["tipo"] == "select_multiple" else [str(valor)]
        fora = [e for e in escolhidos if e and e not in permitidas]
        if fora:
            res.erros.append(onde | {"erro": "fora_da_lista", "mensagem": "valor fora das opções",
                                     "valores": fora})
            return
    if no.get("restricao"):
        v, erro = _avaliar(no["restricao"], ctx | {"_valor": valor_para_contexto(no, valor)})
        if erro or not _verdadeiro(v):
            res.erros.append(onde | {"erro": "restricao_violada", "mensagem": _mensagem(no, doc)}
                             | ({"expressao": erro} if erro else {}))


def _por_nome(doc: dict) -> dict[str, dict]:
    if "_por_nome" not in doc:
        doc["_por_nome"] = {c["nome"]: c for c, _r in folhas(doc["campos"])}
    return doc["_por_nome"]


def avaliar_resposta(doc: dict, valores: dict, repeticoes: dict[str, list[dict]] | None = None) -> Resultado:
    """Calcula, aplica relevância e valida. `valores`/`repeticoes` são copiados; o resultado traz os valores
    finais (cálculos preenchidos, não relevantes anulados)."""
    doc = dict(doc)
    doc.pop("_por_nome", None)
    nomes_rep = {n["nome"] for n in nos(doc["campos"]) if n["tipo"] == "repeticao"}
    vals = {k: v for k, v in (valores or {}).items() if k in _por_nome(doc)}
    reps = {k: [dict(linha) for linha in v] for k, v in (repeticoes or {}).items() if k in nomes_rep}
    for n in nomes_rep:
        reps.setdefault(n, [])
    _calcular(doc, vals, reps)
    res = Resultado(vals, reps)
    ctx = contexto_de(doc, vals, reps)
    for no in doc["campos"]:
        _validar_no(no, doc, vals, ctx, res, True)
    return res
