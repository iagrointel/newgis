"""Conversão `plat_construtor` -> SLD 1.0 (item L2-02-a-modelo-estilo; C2 do L2_CONCEITO): subconjunto
declarado, só para os tipos `unico`, `categoria` e `classes` sobre geometria `ponto`/`linha`/`poligono`
(os que têm equivalente direto em `PointSymbolizer`/`LineSymbolizer`/`PolygonSymbolizer` do OGC SLD 1.0.0).
`proporcional`, `calor`, `agrupamento` e `raster` são declarados FORA (sem `RasterSymbolizer` aqui —
é outro item) e `sld_suportado()` diz a quem chama se dá para converter antes de tentar.

Usado pelo WMS do L2-04-i e pela exportação para QGIS. O teste deste item confere as cores por
LEITURA do XML gerado (`xml.etree.ElementTree`), porque a máquina do laço não tem QGIS instalado
(ver `docs/ADR` e o handoff) — a prova de "abre no QGIS com as mesmas cores" fica pendente de máquina
com QGIS, não escondida."""

from __future__ import annotations

from xml.sax.saxutils import escape

from app.estilos import compilador

SLD_SUPORTADOS = ("unico", "categoria", "classes")
_NS = {
    "xmlns": "http://www.opengis.net/sld",
    "xmlns:ogc": "http://www.opengis.net/ogc",
    "xmlns:se": "http://www.opengis.net/se",
    "version": "1.0.0",
}


class SldNaoSuportado(ValueError):
    pass


def sld_suportado(pc: dict) -> bool:
    return pc.get("tipo") in SLD_SUPORTADOS


def _filtro_ogc(campo: str, valor) -> str:
    if isinstance(valor, bool):
        v = "true" if valor else "false"
    else:
        v = escape(str(valor))
    return (
        f"<ogc:Filter><ogc:PropertyIsEqualTo>"
        f"<ogc:PropertyName>{escape(campo)}</ogc:PropertyName><ogc:Literal>{v}</ogc:Literal>"
        f"</ogc:PropertyIsEqualTo></ogc:Filter>"
    )


def _filtro_faixa(campo: str, mn: float, mx: float, ultima: bool) -> str:
    sup_op = "ogc:PropertyIsLessThanOrEqualTo" if ultima else "ogc:PropertyIsLessThan"
    return (
        "<ogc:Filter><ogc:And>"
        f"<ogc:PropertyIsGreaterThanOrEqualTo><ogc:PropertyName>{escape(campo)}</ogc:PropertyName>"
        f"<ogc:Literal>{mn}</ogc:Literal></ogc:PropertyIsGreaterThanOrEqualTo>"
        f"<{sup_op}><ogc:PropertyName>{escape(campo)}</ogc:PropertyName>"
        f"<ogc:Literal>{mx}</ogc:Literal></{sup_op}>"
        "</ogc:And></ogc:Filter>"
    )


def _symbolizer(geometria: str, cor: str, simbolo: dict) -> str:
    if geometria == "ponto":
        raio = simbolo.get("raio", 4)
        return (
            "<PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>"
            f'<Fill><CssParameter name="fill">{cor}</CssParameter></Fill></Mark>'
            f"<Size>{raio * 2}</Size></Graphic></PointSymbolizer>"
        )
    if geometria == "linha":
        largura = simbolo.get("largura", 1.5)
        return (
            f'<LineSymbolizer><Stroke><CssParameter name="stroke">{cor}</CssParameter>'
            f'<CssParameter name="stroke-width">{largura}</CssParameter></Stroke></LineSymbolizer>'
        )
    contorno = simbolo.get("contorno_cor", "#1d3c34")
    return (
        f'<PolygonSymbolizer><Fill><CssParameter name="fill">{cor}</CssParameter></Fill>'
        f'<Stroke><CssParameter name="stroke">{contorno}</CssParameter></Stroke></PolygonSymbolizer>'
    )


def gerar_sld(pc: dict, nome_camada: str = "camada") -> str:
    """Gera o XML SLD 1.0 completo de um `plat_construtor` suportado. Levanta `SldNaoSuportado` para
    os tipos fora do subconjunto (proporcional/calor/agrupamento/raster)."""
    if not sld_suportado(pc):
        raise SldNaoSuportado(f"tipo {pc.get('tipo')!r} não tem conversão SLD (subconjunto declarado)")
    geometria = pc["geometria"]
    simbolo = pc.get("simbolo") or {}
    cls = compilador.classes(pc)
    campo = pc.get("campo")

    regras = []
    if pc["tipo"] == "unico":
        simb_xml = _symbolizer(geometria, cls[0]["cor"], simbolo)
        regras.append(f"<Rule><Name>{escape(cls[0]['rotulo'])}</Name>{simb_xml}</Rule>")
    elif pc["tipo"] == "categoria":
        for c, entrada in zip(pc["categorias"], cls, strict=False):
            filtro = _filtro_ogc(campo, c["valor"])
            regras.append(
                f"<Rule><Name>{escape(entrada['rotulo'])}</Name>{filtro}"
                f"{_symbolizer(geometria, entrada['cor'], simbolo)}</Rule>"
            )
    else:  # classes
        n = len(pc["classes"])
        for i, (c, entrada) in enumerate(zip(pc["classes"], cls, strict=False)):
            filtro = _filtro_faixa(campo, c["min"], c["max"], ultima=(i == n - 1))
            regras.append(
                f"<Rule><Name>{escape(entrada['rotulo'])}</Name>{filtro}"
                f"{_symbolizer(geometria, entrada['cor'], simbolo)}</Rule>"
            )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" '
        'xmlns:ogc="http://www.opengis.net/ogc" xmlns:se="http://www.opengis.net/se" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.0.0">'
        f"<NamedLayer><Name>{escape(nome_camada)}</Name><UserStyle><Title>{escape(nome_camada)}</Title>"
        f"<FeatureTypeStyle>{''.join(regras)}</FeatureTypeStyle></UserStyle></NamedLayer>"
        "</StyledLayerDescriptor>"
    )
