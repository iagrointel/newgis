"""Estilo da camada como SLD 1.0.0 (item L2-01-l, cláusula "estilo da camada como JSON MapLibre e como
SLD 1.0"; o item L2-04-i é quem publica o mesmo SLD no serviço OGC).

A regra que este módulo respeita é a mesma da legenda (`app/mapa/simbologia.py`): **uma lista de classes
só**. O SLD não é escrito de novo a partir da simbologia — ele é gerado da MESMA função `classes()` que
alimenta o MapLibre e a legenda. Se a cor divergisse entre o mapa da tela e o SLD entregue ao QGIS/
GeoServer, o usuário teria dois mapas diferentes com o mesmo nome; o teste `tests/unit/test_sld.py`
compara as cores das duas saídas.

Escolhas do formato, com a razão:

* **1.0.0, não 1.1.0/SE.** É a versão que QGIS, GeoServer e ArcGIS leem sem conversa; a 1.1.0 troca
  `CssParameter` por `SvgParameter` e nem todo leitor aceita. Quem precisa da 1.1 converte.
* **`ElseFilter` para a classe do resto.** A última classe da simbologia (`teste = None`, "outros" ou
  ">= último corte") não tem filtro próprio: no SLD isso é `<ElseFilter/>`, e não uma regra sem filtro
  (que casaria com TUDO e pintaria o mapa inteiro da cor do resto).
* **XML montado por `xml.etree.ElementTree`**, nunca por concatenação de texto: rótulo de classe vem de
  dado do usuário (valor único de um campo) e precisa de escape de `&`, `<` e aspas. É a mesma razão pela
  qual nenhum literal do filtro entra em texto de SQL neste repositório.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.mapa.simbologia import classes, familia, normalizar

SLD = "http://www.opengis.net/sld"
OGC = "http://www.opengis.net/ogc"
XLINK = "http://www.w3.org/1999/xlink"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
VERSAO = "1.0.0"


def _css(pai: ET.Element, nome: str, valor) -> None:
    e = ET.SubElement(pai, f"{{{SLD}}}CssParameter", {"name": nome})
    e.text = str(valor)


def _filtro(regra: ET.Element, teste, campo: str | None) -> None:
    """Traduz o `teste` da classe (expressão MapLibre) para `ogc:Filter`. Só as duas formas que
    `simbologia.classes()` produz: igualdade de valor único e "menor que" de intervalo."""
    if not teste:
        ET.SubElement(regra, f"{{{SLD}}}ElseFilter")
        return
    f = ET.SubElement(regra, f"{{{OGC}}}Filter")
    op, alvo, valor = teste[0], teste[1], teste[2]
    nome_campo = campo or (alvo[1] if isinstance(alvo, list) and len(alvo) > 1 else "")
    if isinstance(alvo, list) and alvo and alvo[0] == "to-number":
        nome_campo = alvo[1][1]
    tag = {"==": "PropertyIsEqualTo", "<": "PropertyIsLessThan"}[op]
    comp = ET.SubElement(f, f"{{{OGC}}}{tag}")
    ET.SubElement(comp, f"{{{OGC}}}PropertyName").text = str(nome_campo)
    ET.SubElement(comp, f"{{{OGC}}}Literal").text = "" if valor is None else str(valor)


def _simbolizador(regra: ET.Element, fam: str, cor: str, simb: dict) -> None:
    if fam == "Point":
        s = ET.SubElement(regra, f"{{{SLD}}}PointSymbolizer")
        g = ET.SubElement(s, f"{{{SLD}}}Graphic")
        m = ET.SubElement(g, f"{{{SLD}}}Mark")
        ET.SubElement(m, f"{{{SLD}}}WellKnownName").text = "circle"
        _css(ET.SubElement(m, f"{{{SLD}}}Fill"), "fill", cor)
        # o raio do MapLibre é metade do diâmetro que o SLD chama de Size
        ET.SubElement(g, f"{{{SLD}}}Size").text = str(float(simb.get("tamanho", 4)) * 2)
        return
    if fam == "LineString":
        s = ET.SubElement(regra, f"{{{SLD}}}LineSymbolizer")
        t = ET.SubElement(s, f"{{{SLD}}}Stroke")
        _css(t, "stroke", cor)
        _css(t, "stroke-width", float(simb.get("largura", 1.5)))
        _css(t, "stroke-opacity", float(simb.get("opacidade", 0.95)))
        return
    s = ET.SubElement(regra, f"{{{SLD}}}PolygonSymbolizer")
    preench = ET.SubElement(s, f"{{{SLD}}}Fill")
    _css(preench, "fill", cor)
    _css(preench, "fill-opacity", float(simb.get("opacidade", 0.55)))
    traco = ET.SubElement(s, f"{{{SLD}}}Stroke")
    _css(traco, "stroke", simb.get("contorno") or "#1d3c34")
    _css(traco, "stroke-width", 0.6)


def gerar(simb: dict | None, geometria: str | None, *, nome: str, titulo: str = "") -> str:
    """SLD 1.0.0 (texto XML, com declaração) da simbologia da camada."""
    simb = normalizar(simb, geometria)
    fam = familia(geometria)
    cls = classes(simb, geometria)
    campo = simb.get("campo")
    ET.register_namespace("", SLD)
    ET.register_namespace("ogc", OGC)
    ET.register_namespace("xlink", XLINK)
    ET.register_namespace("xsi", XSI)
    raiz = ET.Element(f"{{{SLD}}}StyledLayerDescriptor", {"version": VERSAO})
    camada = ET.SubElement(raiz, f"{{{SLD}}}NamedLayer")
    ET.SubElement(camada, f"{{{SLD}}}Name").text = nome
    estilo = ET.SubElement(camada, f"{{{SLD}}}UserStyle")
    ET.SubElement(estilo, f"{{{SLD}}}Name").text = nome
    ET.SubElement(estilo, f"{{{SLD}}}Title").text = titulo or nome
    fts = ET.SubElement(estilo, f"{{{SLD}}}FeatureTypeStyle")
    for i, c in enumerate(cls):
        regra = ET.SubElement(fts, f"{{{SLD}}}Rule")
        ET.SubElement(regra, f"{{{SLD}}}Name").text = f"classe-{i + 1}"
        ET.SubElement(regra, f"{{{SLD}}}Title").text = str(c["rotulo"])
        if len(cls) > 1:
            _filtro(regra, c["teste"], campo)
        _simbolizador(regra, fam, c["cor"], simb)
    ET.indent(raiz, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(raiz, encoding="unicode") + "\n"


__all__ = ["VERSAO", "gerar"]
