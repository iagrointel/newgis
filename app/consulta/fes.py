"""Filter Encoding 2.0 (OGC 09-026r2, o `FILTER=` do WFS 2.0) e o subconjunto 1.1 que o WFS 1.1.0
manda — traduzido para a MESMA árvore sintática do `cql2.py` e compilado pelo MESMO
`cql2.compilar`. Não existe segundo gerador de SQL nesta casa: o que garante que nenhum texto do
cliente entra concatenado numa consulta é o compilador do CQL2 (literal sempre vira parâmetro
`%s`, coluna sempre sai de lista branca), e o FES só produz nós daquela árvore.

Cobertura (o portão do item L2-04-h pede comparação, lógica, espacial e temporal):
  comparação - PropertyIsEqualTo/NotEqualTo/LessThan/GreaterThan/LessThanOrEqualTo/
               GreaterThanOrEqualTo/Like/Between/Null/Nil
  lógica     - And/Or/Not (aninhadas, com teto de profundidade)
  espacial   - BBOX, Intersects, Within, DWithin (distância em metros)
  temporal   - After, Before, During
  identidade - fes:ResourceId (2.0) e ogc:FeatureId/GmlObjectId (1.1), que é como a consulta
               armazenada GetFeatureById chega aqui

Segurança: o XML é lido por `defusedxml` (entidade externa, DTD e bomba de entidade recusadas na
biblioteca, não por regex nossa), o documento tem teto de bytes, de nós e de profundidade, e a
geometria do filtro só é aceita em CRS geográfico WGS84 (o compilador do CQL2 monta
`ST_GeomFromGeoJSON` em 4326; aceitar outro CRS aqui seria mentir sobre a projeção).

Ordem dos eixos (a pegadinha do WFS 2.0): em `urn:ogc:def:crs:EPSG::4326` e
`http://www.opengis.net/def/crs/EPSG/0/4326` vale a ordem da autoridade EPSG, que para CRS
geográfico é LATITUDE, LONGITUDE. Na forma curta `EPSG:4326` e em `CRS84` vale longitude,
latitude. `_ordem_lat_lon` decide por essa regra e é o único lugar onde ela mora.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

import defusedxml.ElementTree as ET  # noqa: N817 - nome da biblioteca

from app.consulta import cql2

MAX_BYTES = 64 * 1024
MAX_NOS = 500
MAX_PROFUNDIDADE = 20

NS_FES20 = "http://www.opengis.net/fes/2.0"
NS_OGC11 = "http://www.opengis.net/ogc"
NS_GML32 = "http://www.opengis.net/gml/3.2"
NS_GML31 = "http://www.opengis.net/gml"

_COMPARACAO = {
    "PropertyIsEqualTo": "=",
    "PropertyIsNotEqualTo": "<>",
    "PropertyIsLessThan": "<",
    "PropertyIsGreaterThan": ">",
    "PropertyIsLessThanOrEqualTo": "<=",
    "PropertyIsGreaterThanOrEqualTo": ">=",
}
_ESPACIAL = {"Intersects": "s_intersects", "Within": "s_within", "DWithin": "s_dwithin"}
_TEMPORAL = {"After": "t_after", "Before": "t_before", "During": "t_during"}
# CRS geográficos em que a ordem da autoridade EPSG é latitude, longitude
_GEOGRAFICOS_LAT_LON = {4326, 4674, 4258, 4979, 4989}
# só estes são aceitos como CRS da geometria do filtro (o compilador do CQL2 monta em 4326)
_CRS_FILTRO_ACEITOS = {4326, None}
_UOM_METRO = {"m", "metre", "metres", "meter", "meters", "urn:ogc:def:uom:EPSG::9001",
              "http://www.opengis.net/def/uom/OGC/1.0/metre"}
_EPSG_RE = re.compile(r"(?:^|[:/])(?:EPSG)[:/]{1,2}(?:\d+(?:\.\d+)?[:/])?(\d+)$", re.IGNORECASE)


class ErroFes(Exception):
    """Mesma forma de `cql2.ErroCql2` (código + mensagem + detalhe) para a rota traduzir em
    `ows:ExceptionReport` sem saber de onde veio."""

    def __init__(self, codigo: str, mensagem: str, detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# --------------------------------------------------------------------------------- CRS e ordem de eixo
def srid_de_srsname(srs: str | None) -> int | None:
    """`urn:ogc:def:crs:EPSG::4326`, `http://www.opengis.net/def/crs/EPSG/0/4326`, `EPSG:4326`,
    `CRS84` -> 4326. Devolve None quando não há srsName (o WFS manda usar o CRS padrão do tipo)."""
    if not srs:
        return None
    s = srs.strip()
    if s.upper().endswith("CRS84") or s.upper() == "CRS:84":
        return 4326
    m = _EPSG_RE.search(s)
    if m:
        return int(m.group(1))
    if s.isdigit():
        return int(s)
    raise ErroFes("srsname_invalido", f"srsName não reconhecido: {srs!r}", {"srsName": srs})


def _ordem_lat_lon(srs: str | None) -> bool:
    """True quando as coordenadas do documento vêm em (latitude, longitude)."""
    if not srs:
        return False
    s = srs.strip()
    if s.upper().endswith("CRS84") or s.upper() == "CRS:84":
        return False
    if not (s.lower().startswith("urn:") or s.lower().startswith("http")):
        return False  # forma curta EPSG:4326 = longitude, latitude (uso histórico, o que GeoServer faz)
    srid = srid_de_srsname(s)
    return srid in _GEOGRAFICOS_LAT_LON


def _exigir_crs_do_filtro(srs: str | None) -> None:
    srid = srid_de_srsname(srs)
    if srid not in _CRS_FILTRO_ACEITOS:
        raise ErroFes(
            "srsname_nao_suportado",
            f"geometria de filtro só é aceita em WGS84 (CRS84/EPSG:4326); recebido {srs!r}",
            {"srsName": srs},
        )


# --------------------------------------------------------------------------------- leitura do XML
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def ler_xml(texto: str | bytes):
    """Ponto único de entrada de XML de cliente neste módulo — `defusedxml` recusa DTD, entidade
    externa e bomba de entidade; o teto de bytes vem antes para não gastar memória à toa."""
    bruto = texto.encode("utf-8") if isinstance(texto, str) else texto
    if len(bruto) > MAX_BYTES:
        raise ErroFes("filtro_grande_demais", f"documento XML acima do teto de {MAX_BYTES} bytes",
                      {"bytes": len(bruto)})
    try:
        return ET.fromstring(bruto, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except ET.EntitiesForbidden as e:
        raise ErroFes("xml_entidade_proibida", "entidade em XML não é aceita (proteção contra XXE)") from e
    except ET.DTDForbidden as e:
        raise ErroFes("xml_dtd_proibida", "DTD em XML não é aceita (proteção contra XXE)") from e
    except ET.ExternalReferenceForbidden as e:
        raise ErroFes("xml_referencia_externa_proibida", "referência externa em XML não é aceita") from e
    except ET.ParseError as e:
        raise ErroFes("xml_invalido", f"XML malformado: {e}") from e


def _contar(no, limite: int = MAX_NOS) -> int:
    n = 1
    for filho in no:
        n += _contar(filho, limite)
        if n > limite:
            raise ErroFes("filtro_grande_demais", f"filtro com mais de {limite} elementos")
    return n


# --------------------------------------------------------------------------------- geometria GML -> GeoJSON
def _numeros(texto: str | None) -> list[float]:
    if not texto:
        return []
    try:
        return [float(x) for x in texto.replace(",", " ").split()]
    except ValueError as e:
        raise ErroFes("gml_invalido", "lista de coordenadas com valor não numérico") from e


def _pares(vals: list[float], lat_lon: bool) -> list[list[float]]:
    if len(vals) < 2 or len(vals) % 2:
        raise ErroFes("gml_invalido", "lista de coordenadas precisa de pares (x y)")
    pares = [[vals[i], vals[i + 1]] for i in range(0, len(vals), 2)]
    return [[b, a] for a, b in pares] if lat_lon else pares


def _pos_list(no, lat_lon: bool) -> list[list[float]]:
    """Aceita `gml:posList`, vários `gml:pos` e o `gml:coordinates` do GML 3.1 (WFS 1.1)."""
    for filho in no.iter():
        if _local(filho.tag) == "posList":
            return _pares(_numeros(filho.text), lat_lon)
    poss = [f for f in no.iter() if _local(f.tag) == "pos"]
    if poss:
        vals: list[float] = []
        for p in poss:
            vals += _numeros(p.text)
        return _pares(vals, lat_lon)
    for filho in no.iter():
        if _local(filho.tag) == "coordinates":
            texto = (filho.text or "").replace(",", " ")
            return _pares(_numeros(texto), lat_lon)
    raise ErroFes("gml_invalido", "geometria sem gml:posList/gml:pos/gml:coordinates")


def geometria_para_geojson(no) -> dict:
    """gml:Envelope/Point/LineString/Polygon -> dict GeoJSON em longitude, latitude (o que o
    `cql2.compilar` espera)."""
    nome = _local(no.tag)
    srs = no.get("srsName")
    _exigir_crs_do_filtro(srs)
    lat_lon = _ordem_lat_lon(srs)
    if nome == "Envelope":
        canto: dict[str, list[float]] = {}
        for filho in no:
            if _local(filho.tag) in ("lowerCorner", "upperCorner"):
                canto[_local(filho.tag)] = _numeros(filho.text)
        if "lowerCorner" not in canto or "upperCorner" not in canto:
            raise ErroFes("gml_invalido", "gml:Envelope exige lowerCorner e upperCorner")
        (x0, y0), (x1, y1) = (
            _pares(canto["lowerCorner"][:2], lat_lon)[0],
            _pares(canto["upperCorner"][:2], lat_lon)[0],
        )
        return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
    if nome == "Point":
        return {"type": "Point", "coordinates": _pos_list(no, lat_lon)[0]}
    if nome in ("LineString", "Curve", "LinearRing"):
        return {"type": "LineString", "coordinates": _pos_list(no, lat_lon)}
    if nome in ("Polygon", "Surface"):
        aneis = []
        for parte in no.iter():
            if _local(parte.tag) in ("exterior", "interior", "outerBoundaryIs", "innerBoundaryIs"):
                aneis.append(_pos_list(parte, lat_lon))
        if not aneis:
            raise ErroFes("gml_invalido", "gml:Polygon sem anel exterior")
        for anel in aneis:
            if anel[0] != anel[-1]:
                anel.append(list(anel[0]))
        return {"type": "Polygon", "coordinates": aneis}
    raise ErroFes("gml_nao_suportado", f"geometria GML não suportada em filtro: {nome!r}",
                  {"elemento": nome})


# --------------------------------------------------------------------------------- literais e instantes
def _instante(texto: str):
    t = (texto or "").strip()
    if not t:
        raise ErroFes("filtro_sintaxe", "instante temporal vazio")
    try:
        if len(t) == 10:
            return datetime.date.fromisoformat(t)
        return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError as e:
        raise ErroFes("filtro_sintaxe", f"instante temporal fora do ISO 8601: {texto!r}") from e


def _literal(texto: str | None):
    """FES não tipa o literal; a comparação vira `coluna <op> %s` e o Postgres converte pelo tipo
    da coluna. Número vira número (para a coluna numérica não precisar de conversão de texto)."""
    if texto is None:
        return None
    t = texto.strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return texto


def _valor_de(no, nome_elemento: str):
    for filho in no:
        if _local(filho.tag) == nome_elemento:
            return filho
    return None


def _propriedade(no) -> cql2.Propriedade:
    for filho in no:
        if _local(filho.tag) in ("ValueReference", "PropertyName"):
            nome = (filho.text or "").strip()
            if ":" in nome:
                nome = nome.rsplit(":", 1)[1]
            if "/" in nome:
                nome = nome.rsplit("/", 1)[1]
            if not cql2.IDENT_RE.match(nome):
                raise ErroFes("filtro_campo_invalido", f"nome de propriedade inválido: {nome!r}")
            return cql2.Propriedade(nome)
    raise ErroFes("filtro_sintaxe", f"{_local(no.tag)} sem fes:ValueReference")


def _como_like(padrao: str, coringa: str, um: str, escape: str) -> str:
    """Converte o padrão FES (coringas declarados no próprio elemento) para o padrão LIKE do SQL,
    escapando o que é coringa em SQL e não em FES."""
    saida = []
    i = 0
    while i < len(padrao):
        c = padrao[i]
        if escape and c == escape and i + 1 < len(padrao):
            prox = padrao[i + 1]
            saida.append("\\" + prox if prox in ("%", "_", "\\") else prox)
            i += 2
            continue
        if coringa and c == coringa:
            saida.append("%")
        elif um and c == um:
            saida.append("_")
        elif c in ("%", "_", "\\"):
            saida.append("\\" + c)
        else:
            saida.append(c)
        i += 1
    return "".join(saida)


# --------------------------------------------------------------------------------- FES -> AST do CQL2
def _no(elem, profundidade: int = 0):
    if profundidade > MAX_PROFUNDIDADE:
        raise ErroFes("filtro_profundo_demais", f"filtro além de {MAX_PROFUNDIDADE} níveis")
    nome = _local(elem.tag)
    if nome == "And":
        return cql2.E(termos=[_no(f, profundidade + 1) for f in elem])
    if nome == "Or":
        return cql2.Ou(termos=[_no(f, profundidade + 1) for f in elem])
    if nome == "Not":
        filhos = list(elem)
        if len(filhos) != 1:
            raise ErroFes("filtro_sintaxe", "fes:Not exige exatamente um operando")
        return cql2.Nao(termo=_no(filhos[0], profundidade + 1))
    if nome in _COMPARACAO:
        campo = _propriedade(elem)
        lit = _valor_de(elem, "Literal")
        if lit is None:
            raise ErroFes("filtro_sintaxe", f"{nome} sem fes:Literal")
        return cql2.Comparacao(op=_COMPARACAO[nome], operando=campo, valor=_literal(lit.text))
    if nome == "PropertyIsLike":
        campo = _propriedade(elem)
        lit = _valor_de(elem, "Literal")
        if lit is None:
            raise ErroFes("filtro_sintaxe", "PropertyIsLike sem fes:Literal")
        padrao = _como_like(
            lit.text or "",
            elem.get("wildCard", "*"),
            elem.get("singleChar", elem.get("singleCharacter", "?")),
            elem.get("escapeChar", elem.get("escape", "\\")),
        )
        return cql2.Comparacao(op="like", operando=campo, valor=padrao)
    if nome == "PropertyIsBetween":
        campo = _propriedade(elem)
        inf, sup = _valor_de(elem, "LowerBoundary"), _valor_de(elem, "UpperBoundary")
        if inf is None or sup is None:
            raise ErroFes("filtro_sintaxe", "PropertyIsBetween exige LowerBoundary e UpperBoundary")
        return cql2.Comparacao(
            op="between", operando=campo,
            valor=_literal("".join(inf.itertext()).strip()),
            valor2=_literal("".join(sup.itertext()).strip()),
        )
    if nome in ("PropertyIsNull", "PropertyIsNil"):
        return cql2.Comparacao(op="is_null", operando=_propriedade(elem))
    if nome == "BBOX":
        geo = _geometria_do_operador(elem)
        campo = _propriedade_geometria(elem)
        return cql2.Espacial(op="s_intersects", operando=campo, geometria=geo)
    if nome in _ESPACIAL:
        geo = _geometria_do_operador(elem)
        campo = _propriedade_geometria(elem)
        distancia = None
        if nome == "DWithin":
            d = _valor_de(elem, "Distance")
            if d is None:
                raise ErroFes("filtro_sintaxe", "fes:DWithin exige fes:Distance")
            uom = (d.get("uom") or d.get("units") or "m").strip()
            if uom not in _UOM_METRO:
                raise ErroFes("filtro_uom_nao_suportado",
                              f"distância só é aceita em metros; recebido uom={uom!r}", {"uom": uom})
            try:
                distancia = float((d.text or "").strip())
            except ValueError as e:
                raise ErroFes("filtro_sintaxe", "fes:Distance não numérica") from e
        return cql2.Espacial(op=_ESPACIAL[nome], operando=campo, geometria=geo, distancia=distancia)
    if nome in _TEMPORAL:
        campo = _propriedade(elem)
        return cql2.Temporal(op=_TEMPORAL[nome], operando=campo, valor=_tempo_do_operador(elem, nome))
    raise ErroFes("filtro_operador_desconhecido", f"operador FES não suportado: {nome!r}",
                  {"operador": nome})


def _propriedade_geometria(elem) -> cql2.Propriedade:
    """Operador espacial sem `ValueReference` é legal em FES (vale a geometria padrão do tipo);
    aqui a geometria padrão é sempre a coluna `geom`, que o chamador mapeia em `colunas_sql`."""
    try:
        return _propriedade(elem)
    except ErroFes:
        return cql2.Propriedade("geometria")


def _geometria_do_operador(elem) -> dict:
    for filho in elem:
        if _local(filho.tag) in ("ValueReference", "PropertyName", "Distance"):
            continue
        return geometria_para_geojson(filho)
    raise ErroFes("filtro_sintaxe", f"{_local(elem.tag)} sem geometria GML")


def _tempo_do_operador(elem, nome: str):
    for filho in elem:
        alvo = _local(filho.tag)
        if alvo in ("ValueReference", "PropertyName"):
            continue
        if alvo == "TimeInstant":
            for p in filho.iter():
                if _local(p.tag) == "timePosition":
                    return _instante(p.text)
        if alvo == "TimePeriod":
            inicio = fim = None
            for p in filho:
                lp = _local(p.tag)
                texto = "".join(p.itertext()).strip()
                if lp in ("begin", "beginPosition"):
                    inicio = _instante(texto) if texto else None
                elif lp in ("end", "endPosition"):
                    fim = _instante(texto) if texto else None
            return cql2.IntervaloAberto(inicio=inicio, fim=fim)
        if alvo == "Literal":
            texto = (filho.text or "").strip()
            if "/" in texto:
                a, b = texto.split("/", 1)
                return cql2.IntervaloAberto(
                    inicio=None if a in ("..", "") else _instante(a),
                    fim=None if b in ("..", "") else _instante(b),
                )
            return _instante(texto)
    raise ErroFes("filtro_sintaxe", f"{nome} sem instante nem período")


def ids_de(raiz) -> list[str]:
    """`fes:ResourceId` (2.0) e `ogc:FeatureId`/`ogc:GmlObjectId` (1.1) — a identidade que a
    consulta armazenada GetFeatureById usa. Devolve o rid cru; quem chama tira o prefixo do tipo."""
    saida = []
    for filho in raiz.iter():
        if _local(filho.tag) in ("ResourceId", "FeatureId", "GmlObjectId"):
            rid = filho.get("rid") or filho.get("fid") or filho.get("id")
            if rid:
                saida.append(rid)
    return saida


def analisar(xml_texto: str | bytes) -> tuple[Any, list[str]]:
    """`fes:Filter` -> (nó da AST do CQL2 ou None, lista de rid). Um `Filter` só com ResourceId
    não tem predicado: devolve `(None, [rid...])` e a rota vira aquilo num filtro por identidade."""
    raiz = ler_xml(xml_texto)
    if _local(raiz.tag) != "Filter":
        raise ErroFes("filtro_sintaxe", f"raiz do filtro precisa ser fes:Filter, veio {_local(raiz.tag)!r}")
    _contar(raiz)
    ids = ids_de(raiz)
    predicados = [f for f in raiz if _local(f.tag) not in ("ResourceId", "FeatureId", "GmlObjectId")]
    if not predicados:
        if ids:
            return None, ids
        raise ErroFes("filtro_sintaxe", "fes:Filter vazio")
    if len(predicados) > 1:
        return cql2.E(termos=[_no(p) for p in predicados]), ids
    return _no(predicados[0]), ids


def compilar_fes(xml_texto: str | bytes, colunas_sql: dict, srid_nativo: int,
                 coluna_geom_sql: str = "geom") -> tuple[str | None, list, list[str]]:
    """`(sql, params, ids)` pronto para entrar numa cláusula WHERE parametrizada — o SQL sai do
    `cql2.compilar`, o mesmo do OGC API Features."""
    no, ids = analisar(xml_texto)
    if no is None:
        return None, [], ids
    try:
        sql, params = cql2.compilar(no, colunas_sql, srid_nativo, coluna_geom_sql)
    except cql2.ErroCql2 as e:
        raise ErroFes(e.codigo, e.mensagem, e.detalhe) from e
    return sql, params, ids
