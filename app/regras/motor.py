"""Motor das regras de atributo (item L2-10-d-regras-de-atributo; L2_CONCEITO C5: regra de expressão fica na API,
no caminho único de escrita do L2-03-a, e vale para navegador, FeatureServer, OGC, PWA e lote porque todos passam
por `app.edicao.servico`).

Vocabulário (`dados.regras` da camada, esquema v4 da migração 20260908T0715):
  - `calculo`:   `campo` alvo = valor da `expressao`, ao inserir/atualizar (`eventos`), quando um dos `gatilhos`
                 mudou (sem `gatilhos` = sempre); a `ordem` define a sequência, e o que uma regra calculou entra
                 no contexto das seguintes (encadeamento).
  - `restricao`: `expressao` booleana; falso ou nulo = edição RECUSADA com `codigo` e `mensagem` configurados.
  - `validacao`: `expressao` booleana avaliada sob demanda pelo job `camadas.validar` (nunca na edição); falso =
                 uma linha na tabela de erros e_<hex16> (fid, regra, mensagem, em) e na camada de erros.
  - `campos_virtuais`: só leitura, avaliados na leitura (GET .../feicoes) e disponíveis no contexto das regras.
`habilitada: false` desliga a regra sem apagá-la; `excluir_em_massa: true` a pula quando o lote vem marcado como
importação em massa (`em_massa` no corpo de edição).

Ciclo (refutação do item): regra de cálculo cujo `campo` está nos próprios `gatilhos`, ou cadeia de regras em
que o campo calculado por uma dispara/entra na expressão de outra que por sua vez alimenta a primeira, é recusada
na CONFIGURAÇÃO (`regra_ciclo`), nunca descoberta na edição. Campo virtual não pode referenciar campo virtual.

Nada aqui toca o banco: o motor recebe `dados` da camada e dicionários de atributos e devolve atributos ou erros."""

from __future__ import annotations

import datetime
import decimal
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app import limites
from app.erros import ErroAPI
from app.expressao import avaliador_py as ex

TIPOS = ("calculo", "restricao", "validacao")
EVENTOS = ("inserir", "atualizar")
CAMPOS_SISTEMA = ("fid", "globalid", "versao")  # entram no contexto como só-leitura; nunca são alvo de cálculo
NAO_ALVO = frozenset(
    {*CAMPOS_SISTEMA, "geom", "tenant_id", "criado_em", "atualizado_em", "criado_por", "atualizado_por"}
)
CODIGO_RESTRICAO_PADRAO = "regra_restricao"
CODIGO_VALIDACAO_PADRAO = "regra_validacao"


@dataclass
class Regra:
    id: str
    tipo: str
    expressao: str
    no: Any  # AST da expressão (app.expressao.avaliador_py.No)
    campos_usados: frozenset
    campo: str | None = None
    gatilhos: frozenset = frozenset()
    eventos: frozenset = frozenset(EVENTOS)
    ordem: int = 0
    habilitada: bool = True
    mensagem: str = ""
    codigo: str = CODIGO_RESTRICAO_PADRAO
    excluir_em_massa: bool = False
    nome: str = ""


@dataclass
class Virtual:
    nome: str
    expressao: str
    no: Any
    campos_usados: frozenset
    alias: str = ""


@dataclass
class Compilado:
    regras: list[Regra] = field(default_factory=list)  # já na ordem de avaliação
    virtuais: list[Virtual] = field(default_factory=list)
    campos: frozenset = frozenset()  # nomes dos campos físicos da camada

    @property
    def tem_regras_de_edicao(self) -> bool:
        return any(r.habilitada and r.tipo in ("calculo", "restricao") for r in self.regras)


_cache: dict[str, Compilado] = {}
_CACHE_MAX = 256


def campos_usados(no) -> frozenset:
    """Nomes de `$campo` que aparecem na expressão (para gatilho implícito, ciclo e lista branca)."""
    achados: set[str] = set()

    def andar(n):
        if isinstance(n, ex.Campo):
            achados.add(n.nome)
        elif isinstance(n, ex.Unario):
            andar(n.operando)
        elif isinstance(n, ex.Binario):
            andar(n.esquerda)
            andar(n.direita)
        elif isinstance(n, ex.Chamada):
            for a in n.argumentos:
                andar(a)

    andar(no)
    return frozenset(achados)


def _erro(codigo: str, mensagem: str, detalhe: dict | None = None) -> ErroAPI:
    return ErroAPI(422, codigo, mensagem, detalhe)


def _analisar(texto: str, onde: dict) -> Any:
    if not isinstance(texto, str) or not texto.strip():
        raise _erro("regra_expressao_invalida", "expressão vazia", onde)
    if len(texto) > limites.REGRAS_EXPRESSAO_TEXTO_MAX:
        raise _erro(
            "regra_expressao_invalida", f"expressão acima de {limites.REGRAS_EXPRESSAO_TEXTO_MAX} caracteres", onde
        )
    try:
        return ex.analisar(texto)
    except ex.ErroExpressao as e:
        raise _erro(
            "regra_expressao_invalida", f"expressão inválida: {e}", {**onde, "erro": getattr(e, "codigo", None)}
        ) from e


def compilar(dados: dict) -> Compilado:
    """Valida e compila `dados.regras` + `dados.campos_virtuais` de uma camada. Levanta ErroAPI 422 com código
    nomeado (`regra_invalida`, `regra_expressao_invalida`, `regra_campo_inexistente`, `regra_ciclo`). O resultado
    é cacheado pelo conteúdo (a mesma camada editada 1.000 vezes compila uma vez)."""
    bruto = {"regras": dados.get("regras") or [], "virtuais": dados.get("campos_virtuais") or [],
             "campos": [c.get("nome") for c in (dados.get("campos") or [])]}
    chave = hashlib.sha256(json.dumps(bruto, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    pronto = _cache.get(chave)
    if pronto is not None:
        return pronto
    campos = frozenset(n for n in bruto["campos"] if isinstance(n, str))
    if len(bruto["regras"]) > limites.REGRAS_POR_CAMADA_MAX:
        raise _erro("regra_invalida", f"no máximo {limites.REGRAS_POR_CAMADA_MAX} regras por camada")
    if len(bruto["virtuais"]) > limites.REGRAS_CAMPOS_VIRTUAIS_MAX:
        raise _erro("regra_invalida", f"no máximo {limites.REGRAS_CAMPOS_VIRTUAIS_MAX} campos virtuais por camada")

    virtuais: list[Virtual] = []
    nomes_virtuais: set[str] = set()
    for i, v in enumerate(bruto["virtuais"]):
        onde = {"campo_virtual": v.get("nome"), "posicao": i}
        nome = v.get("nome")
        if not isinstance(nome, str) or not nome:
            raise _erro("regra_invalida", "campo virtual sem nome", onde)
        if nome in campos or nome in NAO_ALVO or nome in nomes_virtuais:
            raise _erro(
                "regra_invalida", f"campo virtual {nome!r} colide com um campo da camada ou repete outro virtual", onde
            )
        no = _analisar(v.get("expressao"), onde)
        usados = campos_usados(no)
        fora = sorted(usados - campos - set(CAMPOS_SISTEMA))
        if fora:
            raise _erro("regra_campo_inexistente",
                        f"campo virtual {nome!r} usa campo inexistente (ou outro campo virtual): {', '.join(fora)}",
                        {**onde, "campos": fora})
        virtuais.append(
            Virtual(nome=nome, expressao=v["expressao"], no=no, campos_usados=usados, alias=v.get("alias") or "")
        )
        nomes_virtuais.add(nome)

    disponiveis = campos | nomes_virtuais | frozenset(CAMPOS_SISTEMA)
    regras: list[Regra] = []
    ids: set[str] = set()
    for i, r in enumerate(bruto["regras"]):
        onde = {"regra": r.get("id"), "posicao": i}
        rid = r.get("id")
        if not isinstance(rid, str) or not rid:
            raise _erro("regra_invalida", "regra sem id", onde)
        if rid in ids:
            raise _erro("regra_invalida", f"id de regra repetido: {rid}", onde)
        ids.add(rid)
        tipo = r.get("tipo")
        if tipo not in TIPOS:
            raise _erro("regra_invalida", f"tipo de regra desconhecido: {tipo!r}", onde)
        no = _analisar(r.get("expressao"), onde)
        usados = campos_usados(no)
        fora = sorted(usados - disponiveis)
        if fora:
            raise _erro("regra_campo_inexistente", f"regra {rid!r} usa campo inexistente: {', '.join(fora)}",
                        {**onde, "campos": fora})
        gatilhos = r.get("gatilhos") or []
        fora_g = sorted(set(gatilhos) - campos - {"geom"})
        if fora_g:
            raise _erro(
                "regra_campo_inexistente", f"regra {rid!r} tem gatilho em campo inexistente: {', '.join(fora_g)}",
                {**onde, "campos": fora_g},
            )
        campo = r.get("campo")
        if tipo == "calculo":
            if not isinstance(campo, str) or campo not in campos:
                raise _erro(
                    "regra_campo_inexistente", f"regra de cálculo {rid!r} exige `campo` existente na camada", onde
                )
            if campo in NAO_ALVO:
                raise _erro("regra_invalida", f"campo {campo!r} é de sistema e não pode ser alvo de cálculo", onde)
            if campo in gatilhos:
                raise _erro(
                    "regra_ciclo", f"regra {rid!r} calcula {campo!r} e dispara por {campo!r}: ciclo",
                    {**onde, "ciclo": [rid]},
                )
        elif campo:
            raise _erro("regra_invalida", f"regra {rid!r} do tipo {tipo} não tem `campo` alvo", onde)
        eventos = frozenset(r.get("eventos") or EVENTOS)
        codigo_padrao = CODIGO_VALIDACAO_PADRAO if tipo == "validacao" else CODIGO_RESTRICAO_PADRAO
        codigo = r.get("codigo") or codigo_padrao
        regras.append(Regra(
            id=rid, tipo=tipo, expressao=r["expressao"], no=no, campos_usados=usados,
            campo=campo if tipo == "calculo" else None,
            gatilhos=frozenset(gatilhos), eventos=eventos, ordem=int(r.get("ordem") or 0),
            habilitada=bool(r.get("habilitada", True)), mensagem=r.get("mensagem") or "", codigo=codigo,
            excluir_em_massa=bool(r.get("excluir_em_massa", False)), nome=r.get("nome") or "",
        ))
    _detectar_ciclos(regras)
    regras.sort(key=lambda x: x.ordem)  # sort é estável: empate mantém a ordem de declaração
    comp = Compilado(regras=regras, virtuais=virtuais, campos=campos)
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[chave] = comp
    return comp


def _detectar_ciclos(regras: list[Regra]) -> None:
    """Grafo regra->regra entre regras de CÁLCULO: A -> B quando o campo que A calcula está nos gatilhos de B ou
    na expressão de B. Qualquer ciclo é `regra_ciclo`, com o caminho no detalhe."""
    calc = [r for r in regras if r.tipo == "calculo"]
    por_campo: dict[str, list[Regra]] = {}
    for r in calc:
        por_campo.setdefault(r.campo, []).append(r)
    arestas: dict[str, list[str]] = {r.id: [] for r in calc}
    for a in calc:
        for b in calc:
            if a is b:
                continue
            if a.campo in b.gatilhos or a.campo in b.campos_usados:
                arestas[a.id].append(b.id)
    cor: dict[str, int] = {}
    pilha: list[str] = []

    def dfs(n: str) -> None:
        cor[n] = 1
        pilha.append(n)
        for m in arestas[n]:
            if cor.get(m, 0) == 1:
                ciclo = pilha[pilha.index(m):] + [m]
                raise _erro("regra_ciclo", "regras de cálculo em ciclo: " + " -> ".join(ciclo), {"ciclo": ciclo})
            if cor.get(m, 0) == 0:
                dfs(m)
        pilha.pop()
        cor[n] = 2

    for r in calc:
        if cor.get(r.id, 0) == 0:
            dfs(r.id)


# ---------------------------------------------------------------- contexto e avaliação
def valor_para_contexto(v: Any) -> Any:
    """Valor do banco -> valor da linguagem (números puros, texto, booleano, nulo, data = ms UTC)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, datetime.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=datetime.UTC)
        return int(v.timestamp() * 1000)
    if isinstance(v, datetime.date):
        return int(datetime.datetime(v.year, v.month, v.day, tzinfo=datetime.UTC).timestamp() * 1000)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return bytes(v).hex()
    if isinstance(v, (list, dict)):
        return v
    return str(v)


def contexto_de(comp: Compilado, linha: dict | None, atributos: dict | None = None) -> dict:
    """Contexto (lista branca) = campos da camada + fid/globalid/versao, valores da linha atual sobrepostos pelos
    atributos novos; campos ausentes entram como nulo (nunca `campo_nao_permitido` por campo da própria camada)."""
    ctx: dict[str, Any] = {c: None for c in comp.campos}
    for c in CAMPOS_SISTEMA:
        ctx[c] = None
    if linha:
        for k, v in linha.items():
            if k in ctx:
                ctx[k] = valor_para_contexto(v)
    if atributos:
        for k, v in atributos.items():
            if k in comp.campos:
                ctx[k] = valor_para_contexto(v)
    for virt in comp.virtuais:
        ctx[virt.nome] = _avaliar(virt.no, ctx, f"campo virtual {virt.nome}")
    return ctx


def _avaliar(no, ctx: dict, onde: str) -> Any:
    try:
        return ex.avaliar(no, ctx)
    except ex.ErroExpressao as e:
        raise _erro("regra_erro_avaliacao", f"{onde}: {e}", {"erro": getattr(e, "codigo", None)}) from e


def valores_virtuais(comp: Compilado, linha: dict) -> dict:
    ctx = contexto_de(comp, linha)
    return {v.nome: ctx[v.nome] for v in comp.virtuais}


def aplicar_edicao(comp: Compilado, atributos: dict, atual: dict | None, operacao: str, *,
                   em_massa: bool = False, geometria_mudou: bool = False) -> tuple[dict, list[str]]:
    """Roda cálculo e restrição para UMA feição no caminho de escrita. Devolve (atributos a gravar, incluindo os
    calculados; ids das regras que rodaram). Restrição falsa/nula = ErroAPI 422 com o código/mensagem da regra."""
    if not comp.tem_regras_de_edicao:
        return atributos, []
    mudados: set[str] = set(atributos.keys())
    if geometria_mudou or operacao == "inserir":
        mudados.add("geom")
    if operacao == "inserir":
        mudados |= comp.campos  # feição nova: todo campo "mudou" (o gatilho por campo só faz sentido em atualização)
    saida = dict(atributos)
    ctx = contexto_de(comp, atual, saida)
    rodaram: list[str] = []
    for r in comp.regras:
        if not r.habilitada or r.tipo == "validacao" or operacao not in r.eventos:
            continue
        if em_massa and r.excluir_em_massa:
            continue
        if r.gatilhos and not (r.gatilhos & mudados):
            continue
        rodaram.append(r.id)
        valor = _avaliar(r.no, ctx, f"regra {r.id}")
        if r.tipo == "calculo":
            saida[r.campo] = valor
            ctx[r.campo] = valor_para_contexto(valor)
            mudados.add(r.campo)
            for virt in comp.virtuais:  # virtual que depende do campo recalculado
                if r.campo in virt.campos_usados:
                    ctx[virt.nome] = _avaliar(virt.no, ctx, f"campo virtual {virt.nome}")
        elif valor is not True:
            raise ErroAPI(422, r.codigo, r.mensagem or f"edição recusada pela regra {r.id}",
                          {"regra": r.id, "resultado": None if valor is None else valor_para_contexto(valor)})
    return saida, rodaram


def avaliar_validacao(comp: Compilado, linha: dict) -> list[dict]:
    """Regras de validação habilitadas sobre uma linha: lista de {regra, codigo, mensagem} para as que falham
    (falso, nulo ou erro de avaliação — o erro também é uma falha registrada, nunca engolida)."""
    regras = [r for r in comp.regras if r.tipo == "validacao" and r.habilitada]
    if not regras:
        return []
    ctx = contexto_de(comp, linha)
    falhas: list[dict] = []
    for r in regras:
        try:
            ok = ex.avaliar(r.no, ctx)
        except ex.ErroExpressao as e:
            falhas.append({"regra": r.id, "codigo": "regra_erro_avaliacao", "mensagem": f"{r.mensagem or r.id}: {e}"})
            continue
        if ok is not True:
            falhas.append({"regra": r.id, "codigo": r.codigo, "mensagem": r.mensagem or f"regra {r.id} não satisfeita"})
    return falhas
