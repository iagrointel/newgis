"""Importação de XLSForm (pyxform) para o documento de formulário (item L2-07-b).

`pyxform.xls2json.parse_file_to_json` lê a planilha (survey/choices/settings) e devolve a árvore com `bind`
(relevant, constraint, calculate, required, readonly), `choice_filter`, `choices` e `label` por idioma. Aqui cada
regra XPath vira texto + AST da linguagem própria por `xpath.traduzir`; o que ficou `fora` é registrado em
`avisos` com o campo, a função e o trecho — a regra some, o campo fica. Nada é descartado em silêncio."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from pyxform.xls2json import parse_file_to_json

from app import limites
from app.coleta import xpath
from app.coleta.documento import META_PG, validar_documento
from app.erros import ErroAPI

TIPOS = {
    "text": "texto", "integer": "inteiro", "decimal": "decimal", "date": "data", "time": "hora",
    "dateTime": "data_hora", "select one": "select_one", "select all that apply": "select_multiple",
    "note": "nota", "calculate": "calculo", "hidden": "oculto", "geopoint": "geoponto", "range": "decimal",
    "acknowledge": "texto", "group": "grupo", "repeat": "repeticao",
}
TIPOS_META = tuple(META_PG)
_VERDADEIRO = ("yes", "true", "true()", "1")


def _rotulo(valor: Any, idioma_padrao: str) -> dict[str, str]:
    if valor is None:
        return {}
    if isinstance(valor, dict):
        return {str(k): str(v) for k, v in valor.items() if v is not None}
    return {idioma_padrao: str(valor)}


def _booleano(valor: Any) -> bool:
    return str(valor or "").strip().lower() in _VERDADEIRO


def _regra(texto: str | None, campo: str, papel: str, avisos: list[dict]) -> dict | None:
    if not texto or not str(texto).strip():
        return None
    try:
        tr = xpath.traduzir(str(texto))
    except xpath.ErroXPath as e:
        raise ErroAPI(422, "xpath_invalido", f"{papel} do campo {campo}: {e.mensagem}",
                      {"campo": campo, "papel": papel, "texto": str(texto), "posicao": e.posicao}) from e
    for a in tr.avisos:
        avisos.append({"campo": campo, "papel": papel} | a.json())
    if tr.texto is None:
        return None
    from app.coleta.documento import regra_de

    return regra_de(tr.texto, origem=str(texto))


def _campo(item: dict, idioma_padrao: str, avisos: list[dict], listas: dict) -> dict | None:
    tipo_x = str(item.get("type") or "")
    nome = str(item.get("name") or "")
    bind = item.get("bind") or {}
    controle = item.get("control") or {}
    if nome == "meta" and controle.get("bodyless"):
        return None  # instanceID: o servidor gera o globalid
    if tipo_x in TIPOS_META:
        tipo = "meta"
    elif tipo_x in TIPOS:
        tipo = TIPOS[tipo_x]
    else:
        tipo = "fora"
        avisos.append({"campo": nome, "papel": "tipo", "funcao": tipo_x, "estado": xpath.FORA,
                       "trecho": tipo_x, "motivo": "tipo de pergunta fora deste item (guardado como texto)"})
    campo: dict[str, Any] = {
        "nome": nome, "tipo": tipo, "tipo_xlsform": tipo_x,
        "rotulo": _rotulo(item.get("label"), idioma_padrao), "dica": _rotulo(item.get("hint"), idioma_padrao),
        "obrigatorio": _booleano(bind.get("required")),
        "somente_leitura": _booleano(bind.get("readonly")),
        "padrao": item.get("default"), "aparencia": controle.get("appearance"),
        "relevante": _regra(bind.get("relevant"), nome, "relevant", avisos),
        "restricao": _regra(bind.get("constraint"), nome, "constraint", avisos),
        "calculo": _regra(bind.get("calculate"), nome, "calculation", avisos),
        "lista": None, "filtro_lista": None, "campo_destino": None,
    }
    if tipo == "meta":
        campo["meta"] = tipo_x
    if campo["restricao"] is not None:
        campo["restricao"]["mensagem"] = _rotulo(bind.get("jr:constraintMsg"), idioma_padrao)
    if tipo in ("select_one", "select_multiple"):
        nome_lista = str(item.get("list_name") or item.get("itemset") or "")
        campo["lista"] = nome_lista or None
        campo["filtro_lista"] = _regra(item.get("choice_filter"), nome, "choice_filter", avisos)
        if nome_lista and nome_lista not in listas and item.get("choices"):
            listas[nome_lista] = _lista(item["choices"], idioma_padrao)
    if tipo in ("grupo", "repeticao"):
        campo["filhos"] = _filhos(item.get("children") or [], idioma_padrao, avisos, listas)
    return campo


def _lista(linhas: list[dict], idioma_padrao: str) -> list[dict]:
    saida = []
    for linha in linhas:
        extras = {k: v for k, v in linha.items() if k not in ("name", "label")}
        saida.append({"nome": str(linha.get("name")), "rotulo": _rotulo(linha.get("label"), idioma_padrao)} | extras)
    return saida


def _filhos(itens: list[dict], idioma_padrao: str, avisos: list[dict], listas: dict) -> list[dict]:
    saida = []
    for item in itens:
        c = _campo(item, idioma_padrao, avisos, listas)
        if c is not None:
            saida.append(c)
    return saida


def importar(conteudo: bytes, nome_arquivo: str) -> dict:
    """Bytes do .xlsx/.xls/.csv -> documento validado (ordem de cálculo e ciclos incluídos)."""
    if len(conteudo) > limites.XLSFORM_TAMANHO_MAX:
        raise ErroAPI(413, "xlsform_grande", f"XLSForm acima de {limites.XLSFORM_TAMANHO_MAX} bytes")
    sufixo = os.path.splitext(nome_arquivo or "")[1].lower()
    if sufixo not in (".xlsx", ".xls", ".csv", ".md"):
        raise ErroAPI(422, "xlsform_formato", "XLSForm tem de ser .xlsx, .xls, .csv ou .md", {"nome": nome_arquivo})
    with tempfile.TemporaryDirectory(prefix="xlsform-") as pasta:
        caminho = os.path.join(pasta, "formulario" + sufixo)
        with open(caminho, "wb") as f:
            f.write(conteudo)
        try:
            bruto = parse_file_to_json(caminho, default_name=os.path.splitext(os.path.basename(nome_arquivo))[0]
                                       or "formulario")
        except Exception as e:  # pyxform levanta PyXFormError e erros de leitura da planilha
            raise ErroAPI(422, "xlsform_invalido", f"XLSForm inválido: {str(e)[:500]}") from e
    idioma_padrao = str(bruto.get("default_language") or "default")
    avisos: list[dict] = []
    listas: dict[str, list[dict]] = {k: _lista(v, idioma_padrao) for k, v in (bruto.get("choices") or {}).items()}
    campos = _filhos(bruto.get("children") or [], idioma_padrao, avisos, listas)
    idiomas: list[str] = []
    for c in campos:
        for k in c.get("rotulo", {}):
            if k not in idiomas:
                idiomas.append(k)
    for linhas in listas.values():
        for linha in linhas:
            for k in linha.get("rotulo", {}):
                if k not in idiomas:
                    idiomas.append(k)
    doc = {
        "versao": 1,
        "nome": str(bruto.get("id_string") or bruto.get("name") or "formulario"),
        "titulo": str(bruto.get("title") or bruto.get("name") or "formulário"),
        "versao_formulario": str(bruto.get("version") or ""),
        "idiomas": idiomas or [idioma_padrao], "idioma_padrao": idioma_padrao,
        "campos": campos, "listas": listas,
        "camada_destino": None, "camadas_filhas": {},
        "ordem_calculo": [], "avisos": avisos,
    }
    return validar_documento(doc)
