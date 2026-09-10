"""Documento de formulário de coleta (item L2-07-b) — o precursor do documento do construtor L5-03.

Forma (JSON gravado em `plat.item.dados` do tipo `formulario`):
  {versao: 1, nome, titulo, versao_formulario, idiomas: [..], idioma_padrao,
   campos: [campo...],                 árvore: grupo/repeticao têm `filhos`
   listas: {nome: [{nome, rotulo: {idioma: texto}, ...colunas extras}]},
   camada_destino: uuid|null, camadas_filhas: {repeticao: uuid},
   ordem_calculo: [nomes], avisos: [{campo, funcao, estado, trecho, motivo}]}
  campo = {nome, tipo, rotulo: {idioma: texto}, dica, obrigatorio, somente_leitura, padrao, aparencia,
           relevante: regra|null, restricao: regra|null (+ mensagem), calculo: regra|null,
           lista: nome|null, filtro_lista: regra|null, campo_destino: coluna|null, filhos: [..]}
  regra = {origem: xpath, texto: linguagem própria, ast: JSON do L2-10-c}

Toda regra é gravada como TEXTO e AST (C6: quem consome usa o AST). As duas implementações do motor (Python aqui,
`web/js/coleta/motor.js` no navegador) avaliam o mesmo AST com o mesmo contexto (convenções em `xpath.py`)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app import limites
from app.erros import ErroAPI
from app.expressao.avaliador_py import ErroExpressao, analisar, ast_para_json

TIPOS_FOLHA = ("texto", "inteiro", "decimal", "data", "hora", "data_hora", "select_one", "select_multiple",
               "nota", "calculo", "oculto", "meta", "geoponto", "fora")
TIPOS_NO = ("grupo", "repeticao")
TIPO_PG = {
    "texto": "text", "inteiro": "integer", "decimal": "double precision", "data": "date", "hora": "time",
    "data_hora": "timestamptz", "select_one": "text", "select_multiple": "text", "calculo": "text",
    "oculto": "text", "fora": "text",
}
META_PG = {"start": "timestamptz", "end": "timestamptz", "today": "date", "username": "text", "deviceid": "text",
           "phonenumber": "text", "email": "text", "simserial": "text", "subscriberid": "text"}
# colunas automáticas de toda camada de destino (hipótese: usuário, dispositivo, início/fim, versão do formulário)
COLUNAS_AUTOMATICAS = (
    ("coleta_inicio", "timestamptz"), ("coleta_fim", "timestamptz"), ("coleta_usuario", "text"),
    ("coleta_dispositivo", "text"), ("coleta_versao", "text"),
)
COLUNAS_REPETICAO = (("pai_globalid", "uuid"), ("indice", "integer"))
_RE_NOME = re.compile(r"^[A-Za-z_][\w-]{0,62}$")
_MS_DIA = 86_400_000


def regra_de(texto: str, origem: str | None = None) -> dict:
    """Texto na linguagem própria -> {origem, texto, ast}. Erro de análise vira 422 nomeado."""
    try:
        no = analisar(texto)
    except ErroExpressao as e:
        raise ErroAPI(422, "expressao_invalida", f"expressão inválida: {e}",
                      {"texto": texto, "codigo": e.codigo}) from e
    return {"origem": origem if origem is not None else texto, "texto": texto, "ast": ast_para_json(no)}


def campos_do_ast(ast: dict | None) -> set[str]:
    """Nomes `$x` referenciados num AST, já traduzidos para nomes de campo (`rep__col` -> `rep`; `_valor`,
    `_linha`, `_lista_*` são do motor, não campos)."""
    saida: set[str] = set()

    def visitar(no):
        if not isinstance(no, dict):
            return
        if no.get("tipo") == "campo":
            nome = no.get("nome", "")
            if nome in ("_valor", "_linha") or nome.startswith("_lista_"):
                return
            saida.add(nome.split("__", 1)[0])
            return
        for v in no.values():
            if isinstance(v, dict):
                visitar(v)
            elif isinstance(v, list):
                for x in v:
                    visitar(x)

    visitar(ast)
    return saida


def folhas(campos: list[dict], repeticao: str | None = None):
    """Percorre a árvore em ordem, devolvendo (campo, nome da repetição que o contém | None)."""
    for c in campos:
        if c.get("tipo") in TIPOS_NO:
            yield from folhas(c.get("filhos") or [], c["nome"] if c["tipo"] == "repeticao" else repeticao)
        else:
            yield c, repeticao


def nos(campos: list[dict]):
    for c in campos:
        yield c
        if c.get("tipo") in TIPOS_NO:
            yield from nos(c.get("filhos") or [])


def ordem_de_calculo(doc: dict) -> list[str]:
    """Ordenação topológica dos campos com `calculo` pelas referências `$x` dos ASTs. Ciclo -> 422
    `dependencia_circular` com os nomes envolvidos (refutação do item)."""
    calculos = {c["nome"]: campos_do_ast((c.get("calculo") or {}).get("ast")) for c in nos(doc["campos"])
                if c.get("calculo")}
    pendentes = {n: {d for d in deps if d in calculos and d != n} for n, deps in calculos.items()}
    ordem: list[str] = []
    while pendentes:
        prontos = sorted(n for n, deps in pendentes.items() if not deps)
        if not prontos:
            raise ErroAPI(422, "dependencia_circular", "cálculo com dependência circular",
                          {"campos": sorted(pendentes)})
        for n in prontos:
            ordem.append(n)
            del pendentes[n]
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return ordem


def validar_documento(doc: dict) -> dict:
    """Limites e nomes; recalcula `ordem_calculo` (e com isso detecta ciclo)."""
    todos = list(nos(doc.get("campos") or []))
    if len(todos) > limites.FORMULARIO_CAMPOS_MAX:
        raise ErroAPI(422, "formulario_grande", f"mais de {limites.FORMULARIO_CAMPOS_MAX} campos")
    vistos: set[str] = set()
    for c in todos:
        nome = c.get("nome") or ""
        if not _RE_NOME.match(nome) or nome.startswith("_"):
            raise ErroAPI(422, "nome_de_campo_invalido", f"nome de campo inválido: {nome!r}")
        if nome in vistos:
            raise ErroAPI(422, "campo_duplicado", f"campo repetido: {nome}")
        vistos.add(nome)
        if c.get("tipo") not in TIPOS_FOLHA + TIPOS_NO:
            raise ErroAPI(422, "tipo_de_campo_invalido", f"tipo desconhecido: {c.get('tipo')!r}", {"campo": nome})
        if c.get("tipo") == "repeticao" and any(f.get("tipo") == "repeticao" for f in nos(c.get("filhos") or [])):
            raise ErroAPI(422, "repeticao_aninhada", "repetição dentro de repetição não é suportada", {"campo": nome})
    for nome, linhas in (doc.get("listas") or {}).items():
        if len(linhas) > limites.FORMULARIO_LISTA_MAX:
            raise ErroAPI(422, "lista_grande", f"lista {nome} acima de {limites.FORMULARIO_LISTA_MAX} linhas")
    doc["ordem_calculo"] = ordem_de_calculo(doc)
    return doc


# ----------------------------------------------------------------------------------------------- avaliação
def _ms_de_data(valor: str) -> int | None:
    try:
        d = dt.date.fromisoformat(valor[:10])
    except ValueError:
        return None
    return (d - dt.date(1970, 1, 1)).days * _MS_DIA


def _ms_de_data_hora(valor: str) -> int | None:
    try:
        t = dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return int(t.timestamp() * 1000)


def valor_para_contexto(campo: dict, valor: Any) -> Any:
    """Mesma conversão do motor JS: data/data-hora viram ms UTC; inteiro/decimal viram número; vazio vira nulo."""
    if valor is None or valor == "":
        return None
    tipo = campo.get("tipo")
    if tipo == "data" and isinstance(valor, str):
        return _ms_de_data(valor)
    if tipo == "data_hora" and isinstance(valor, str):
        return _ms_de_data_hora(valor)
    if tipo in ("inteiro", "decimal"):
        if isinstance(valor, bool):
            return None
        if isinstance(valor, (int, float)):
            return valor
        try:
            return float(valor) if tipo == "decimal" else int(valor)
        except (TypeError, ValueError):
            return None
    if tipo == "meta" and campo.get("meta") in ("start", "end") and isinstance(valor, str):
        return _ms_de_data_hora(valor)
    return valor


def contexto_de(doc: dict, valores: dict, repeticoes: dict[str, list[dict]] | None = None) -> dict:
    """Contexto do nível raiz: `$campo`, `$rep` (linhas), `$rep__col` (colunas) e `$_lista_<nome>`."""
    ctx: dict[str, Any] = {}
    por_nome = {c["nome"]: c for c, _r in folhas(doc["campos"])}
    for c, rep in folhas(doc["campos"]):
        if rep is None:
            ctx[c["nome"]] = valor_para_contexto(c, valores.get(c["nome"]))
    for nome_rep, linhas in (repeticoes or {}).items():
        no_rep = next((n for n in nos(doc["campos"]) if n["nome"] == nome_rep and n["tipo"] == "repeticao"), None)
        if no_rep is None:
            continue
        convertidas = []
        for linha in linhas:
            convertidas.append({f["nome"]: valor_para_contexto(f, linha.get(f["nome"]))
                                for f, _r in folhas(no_rep.get("filhos") or [])})
        ctx[nome_rep] = convertidas
        for f, _r in folhas(no_rep.get("filhos") or []):
            ctx[f"{nome_rep}__{f['nome']}"] = [linha.get(f["nome"]) for linha in convertidas]
    for nome_lista, linhas in (doc.get("listas") or {}).items():
        ctx[f"_lista_{nome_lista}"] = {str(linha.get("nome")): linha for linha in linhas}
    for nome in por_nome:
        ctx.setdefault(nome, None)
    return ctx
