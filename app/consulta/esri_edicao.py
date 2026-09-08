"""Tradução entre o vocabulário de escrita da Esri (applyEdits/addFeatures/attachments/calculate) e a API de
edição da casa (item L2-03-a, `app/edicao/servico.py`), item L2-04-d.

Aqui não há acesso a rota nem a FastAPI: só conversão de forma. A REGRA que organiza o módulo é que nada
escreve por fora da porta única de escrita — o que este arquivo faz é montar o `EdicoesEntrada` que aquela
porta já sabe validar, e depois vestir o resultado com os nomes que o cliente Esri espera.

Geometria: o objeto Esri vira EWKT pelo mesmo `app/consulta/geometria_esri.py` que a operação `query` usa
(números validados um a um, nunca texto colado no SQL) e o EWKT vira GeoJSON no próprio Postgres
(`ST_AsGeoJSON`), porque é o GeoJSON que a porta de escrita valida. Limitação declarada: polígono Esri com
vários anéis EXTERNOS (multipartes) entra como um POLYGON com anéis internos — quem precisa de multiparte
manda `rings` de um anel externo só por feição ou usa a API da casa."""

from __future__ import annotations

import json
import re
from typing import Any

from app.consulta.geometria_esri import MAX_VERTICES, contar_vertices, para_ewkt, sr_wkid
from app.erros import ErroAPI
from app.expressao.avaliador_py import TABELA_FUNCOES

# nomes de campo que o cliente Esri usa para identificar a feição (a casa chama fid/globalid)
NOMES_OBJECTID = ("objectid", "fid")
NOMES_GLOBALID = ("globalid", "global_id")


def valor_por_nome(atributos: dict | None, nomes: tuple[str, ...]) -> Any:
    """Procura a chave sem diferenciar maiúscula (o cliente Esri escreve OBJECTID, ObjectId, objectid)."""
    for chave, valor in (atributos or {}).items():
        if isinstance(chave, str) and chave.lower() in nomes:
            return valor
    return None


def atributos_limpos(atributos: dict | None) -> dict:
    """Tira as chaves de identificação/rastreio: quem manda quem é a feição é o `objectId`/`globalId` do
    envelope, nunca um atributo. A porta de escrita já ignora reservados, isto só evita o aviso inútil."""
    fora = set(NOMES_OBJECTID) | set(NOMES_GLOBALID)
    return {k: v for k, v in (atributos or {}).items() if not (isinstance(k, str) and k.lower() in fora)}


def _tipo_esri_do_objeto(geom: dict) -> str:
    if "x" in geom and "y" in geom:
        return "point"
    if "points" in geom:
        return "multipoint"
    if "paths" in geom:
        return "polyline"
    if "rings" in geom:
        return "polygon"
    if all(k in geom for k in ("xmin", "ymin", "xmax", "ymax")):
        return "envelope"
    raise ErroAPI(400, "geometria_invalida", "geometria Esri sem x/y, points, paths, rings ou xmin..ymax")


def geojson_de_esri(cur, geom: Any, srid_camada: int) -> tuple[dict, int | None]:
    """(GeoJSON, srid declarado pelo cliente ou None). Sem `spatialReference` no objeto, o srid volta None e
    a porta de escrita trata a geometria como já estando no SRID da camada — é exatamente aí que a checagem
    de coordenada fora do intervalo geográfico (L2-03-a) pega o envio em metros sem declarar CRS."""
    if isinstance(geom, str):
        try:
            geom = json.loads(geom)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "geometria_invalida", "geometry não é JSON válido") from e
    if not isinstance(geom, dict):
        raise ErroAPI(400, "geometria_invalida", "geometry precisa ser um objeto")
    tipo = _tipo_esri_do_objeto(geom)
    if contar_vertices(geom, tipo) > MAX_VERTICES:
        raise ErroAPI(400, "geometria_grande", f"geometria acima de {MAX_VERTICES} vértices")
    declarado = sr_wkid(geom.get("spatialReference")) if geom.get("spatialReference") is not None else None
    ewkt = para_ewkt(geom, tipo, declarado or srid_camada)
    cur.execute("SELECT ST_AsGeoJSON(ST_GeomFromEWKT(%s)) AS g", (ewkt,))
    linha = cur.fetchone()
    if not linha or not linha["g"]:
        raise ErroAPI(400, "geometria_invalida", "geometria Esri não pôde ser convertida")
    return json.loads(linha["g"]), declarado


# ---------------------------------------------------------------- resultados e erros no formato Esri
def resultado_ok(object_id: int | None, global_id: str | None, edit_moment: int | None = None) -> dict:
    r: dict[str, Any] = {"objectId": object_id, "globalId": global_id, "success": True}
    if edit_moment is not None:
        r["editMoment"] = edit_moment
    return r


def resultado_erro(object_id: int | None, global_id: str | None, codigo: int, descricao: str) -> dict:
    return {
        "objectId": object_id, "globalId": global_id, "success": False,
        "error": {"code": codigo, "description": descricao},
    }


def erro_do_erroapi(e: ErroAPI) -> dict:
    """`{code, description}` no vocabulário Esri a partir do erro nomeado da casa. O código é o HTTP real
    (a Esri usa o mesmo espaço de números: 400 pedido inválido, 403 sem permissão, 404 inexistente)."""
    return {"code": e.status_code, "description": f"{e.erro}: {e.mensagem}"}


def corpo_erro_esri(codigo: int, mensagem: str, detalhes: list[str] | None = None) -> dict:
    return {"error": {"code": codigo, "message": mensagem, "details": detalhes or []}}


# ---------------------------------------------------------------- calculate: sqlExpression -> L2-03-f
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TEXTO = re.compile(r"'(?:[^']|'')*'")
# fonte única dos nomes de função: a tabela do próprio avaliador (item L2-03-f), nunca uma cópia
_FUNCOES_DA_CASA = {nome.lower(): nome for nome in TABELA_FUNCOES}
_LITERAIS = {"true": "verdadeiro", "false": "falso", "null": "nulo",
             "verdadeiro": "verdadeiro", "falso": "falso", "nulo": "nulo"}


def traduzir_sql_para_expressao(sql: str, campos: set[str]) -> str:
    """`sqlExpression` do `calculate` (nome de coluna cru, como no SQL) reescrito na sintaxe da expressão da
    casa (item L2-03-f, `app/expressao/avaliador_py.py`), onde campo é `$nome`. Só identificador que É campo
    da camada ou função conhecida passa; qualquer outro nome é recusado ANTES de qualquer avaliação — não
    existe caminho por onde o texto do cliente chegue ao banco como SQL."""
    if not isinstance(sql, str) or not sql.strip():
        raise ErroAPI(400, "calc_expressao_vazia", "calcExpression sem sqlExpression nem value")
    minusculos = {c.lower(): c for c in campos}
    saida: list[str] = []
    posicao = 0
    for texto in _TEXTO.finditer(sql):
        saida.append(_reescrever_fora_de_texto(sql[posicao:texto.start()], minusculos))
        saida.append(texto.group(0))
        posicao = texto.end()
    saida.append(_reescrever_fora_de_texto(sql[posicao:], minusculos))
    return "".join(saida)


def _reescrever_fora_de_texto(trecho: str, campos_minusculos: dict[str, str]) -> str:
    def troca(m: re.Match) -> str:
        nome = m.group(0)
        baixo = nome.lower()
        if baixo in campos_minusculos:
            return "$" + campos_minusculos[baixo]
        if baixo in _FUNCOES_DA_CASA:
            return _FUNCOES_DA_CASA[baixo]
        if baixo in _LITERAIS:
            return _LITERAIS[baixo]
        raise ErroAPI(
            400, "calc_nome_desconhecido",
            f"nome não é campo desta camada nem função conhecida: {nome!r}", {"nome": nome},
        )
    return _IDENT.sub(troca, trecho)
