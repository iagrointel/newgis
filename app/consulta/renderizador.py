"""Conversão do estilo MapLibre da camada para o `drawingInfo` do FeatureServer (item L2-04-b).

A plataforma guarda o estilo no vocabulário MapLibre (`type`/`paint`/`layout`), que é o que o visor
web desenha. O ArcGIS Pro, o QGIS pelo conector "ArcGIS REST Server" e o Map Viewer leem o mesmo
desenho pelo `drawingInfo` do descritor da camada. Sem esta ponte, a camada abre no cliente Esri em
cinza — tecnicamente correta, visualmente outra coisa.

São três os desenhos que a Esri chama de renderer e que o MapLibre sabe expressar:

- cor constante                       -> `simple`
- `["match", ["get", campo], v, cor, ..., cor_padrao]`  -> `uniqueValue`
- `["step", ["get", campo], cor, corte, cor, ...]`      -> `classBreaks`

Qualquer outra expressão (interpolate, case aninhado, cor por zoom) NÃO é convertida: devolve
`simple` com a cor padrão e o motivo em `_conversao`. Inventar um renderer aproximado seria pintar
o mapa do cliente com uma classificação que não é a dele.

`layout.text-field` vira `labelingInfo` (rótulo), no formato da Esri (`labelExpressionInfo.expression`
em Arcade, `"$feature.campo"`).

Referência: developers.arcgis.com, "Renderer objects" e "Symbol objects"; maplibre.org, "Style Spec"."""

from __future__ import annotations

import re

# MapLibre type -> família de símbolo da Esri
_SIMBOLO_POR_TIPO = {
    "fill": "esriSFS",
    "line": "esriSLS",
    "circle": "esriSMS",
    "symbol": "esriSMS",
}
_COR_PADRAO = [128, 128, 128, 255]
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_RE = re.compile(r"^rgba?\(([^)]*)\)$")


def cor_para_esri(valor, opacidade: float = 1.0) -> list[int] | None:
    """`#rrggbb`, `#rgb`, `#rrggbbaa`, `rgb()`/`rgba()` -> `[r, g, b, a]` com a de 0 a 255. Fora
    disso devolve None (o chamador decide se cai no padrão ou recusa a conversão)."""
    if isinstance(valor, (list, tuple)) and len(valor) in (3, 4):
        try:
            canais = [int(v) for v in valor[:3]]
        except (TypeError, ValueError):
            return None
        alfa = int(valor[3]) if len(valor) == 4 else 255
        return [*canais, alfa]
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    if _HEX_RE.match(texto):
        h = texto[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        canais = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        alfa = canais[3] if len(canais) == 4 else 255
        return [canais[0], canais[1], canais[2], round(alfa * _fracao(opacidade))]
    m = _RGB_RE.match(texto.lower())
    if m:
        partes = [p.strip() for p in m.group(1).split(",")]
        if len(partes) not in (3, 4):
            return None
        try:
            canais = [int(round(float(p))) for p in partes[:3]]
            alfa = float(partes[3]) if len(partes) == 4 else 1.0
        except ValueError:
            return None
        return [*canais, round(255 * alfa * _fracao(opacidade))]
    return None


def _fracao(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 1.0
    return min(max(f, 0.0), 1.0)


def _simbolo(tipo: str, cor: list[int], paint: dict) -> dict:
    familia = _SIMBOLO_POR_TIPO.get(tipo, "esriSFS")
    contorno = cor_para_esri(paint.get("fill-outline-color"), 1.0) or [110, 110, 110, 255]
    if familia == "esriSFS":
        return {"type": "esriSFS", "style": "esriSFSSolid", "color": cor,
                "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": contorno, "width": 0.4}}
    if familia == "esriSLS":
        largura = paint.get("line-width")
        return {"type": "esriSLS", "style": "esriSLSSolid", "color": cor,
                "width": float(largura) if isinstance(largura, (int, float)) else 1.0}
    raio = paint.get("circle-radius")
    return {"type": "esriSMS", "style": "esriSMSCircle", "color": cor,
            "size": float(raio) * 2 if isinstance(raio, (int, float)) else 8.0,
            "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": contorno, "width": 0.5}}


def _chave_de_cor(tipo: str) -> tuple[str, str]:
    """(propriedade de cor, propriedade de opacidade) do paint, por tipo de camada MapLibre."""
    if tipo == "line":
        return "line-color", "line-opacity"
    if tipo in ("circle", "symbol"):
        return "circle-color", "circle-opacity"
    return "fill-color", "fill-opacity"


def _campo_de(expr) -> str | None:
    """`["get", "classe"]` -> "classe"; qualquer outra forma de entrada -> None."""
    if isinstance(expr, list) and len(expr) == 2 and expr[0] == "get" and isinstance(expr[1], str):
        return expr[1]
    return None


def _rotulo(camada: dict) -> list[dict]:
    layout = camada.get("layout") or {}
    campo = _campo_de(layout.get("text-field"))
    if campo is None and isinstance(layout.get("text-field"), str):
        # forma antiga do MapLibre: "{campo}"
        bruto = layout["text-field"].strip()
        campo = bruto[1:-1] if bruto.startswith("{") and bruto.endswith("}") else None
    if not campo:
        return []
    paint = camada.get("paint") or {}
    cor = cor_para_esri(paint.get("text-color"), 1.0) or [0, 0, 0, 255]
    tamanho = layout.get("text-size")
    return [{
        "labelPlacement": "esriServerPointLabelPlacementCenterCenter",
        "labelExpressionInfo": {"expression": f"$feature.{campo}"},
        "useCodedValues": False,
        "symbol": {"type": "esriTS", "color": cor, "font": {"family": "Arial", "size":
                   float(tamanho) if isinstance(tamanho, (int, float)) else 11.0}},
        "minScale": 0, "maxScale": 0,
    }]


def para_drawing_info(camada: dict | None) -> dict:
    """Estilo MapLibre de UMA camada -> `drawingInfo` do FeatureServer. Entrada vazia/desconhecida
    devolve o renderer `simple` cinza, com `_conversao` dizendo por quê — o cliente Esri desenha
    alguma coisa e quem lê o JSON sabe que não foi conversão fiel."""
    camada = camada or {}
    tipo = camada.get("type") or "fill"
    paint = camada.get("paint") or {}
    chave_cor, chave_opacidade = _chave_de_cor(tipo)
    bruto = paint.get(chave_cor)
    opacidade = paint.get(chave_opacidade, 1.0)
    rotulos = _rotulo(camada)

    def _saida(renderer: dict, conversao: str) -> dict:
        d = {"renderer": renderer, "transparency": round(100 * (1 - _fracao(opacidade))),
             "_conversao": conversao}
        if rotulos:
            d["labelingInfo"] = rotulos
        return d

    if isinstance(bruto, list) and bruto and bruto[0] == "match":
        r = _unique_value(bruto, tipo, paint)
        if r is not None:
            return _saida(r, "uniqueValue de match")
    if isinstance(bruto, list) and bruto and bruto[0] == "step":
        r = _class_breaks(bruto, tipo, paint)
        if r is not None:
            return _saida(r, "classBreaks de step")

    cor = cor_para_esri(bruto, opacidade)
    if cor is not None:
        return _saida({"type": "simple", "symbol": _simbolo(tipo, cor, paint), "label": "", "description": ""},
                      "simple de cor constante")
    motivo = "expressao nao convertida" if isinstance(bruto, list) else "sem cor no estilo"
    return _saida({"type": "simple", "symbol": _simbolo(tipo, list(_COR_PADRAO), paint), "label": "",
                   "description": ""}, motivo)


def _unique_value(expr: list, tipo: str, paint: dict) -> dict | None:
    """`["match", ["get", campo], v1, c1, v2, c2, ..., padrao]`."""
    campo = _campo_de(expr[1] if len(expr) > 1 else None)
    pares = expr[2:-1]
    if campo is None or len(expr) < 4 or len(pares) % 2 != 0:
        return None
    infos = []
    for valor, cor_bruta in zip(pares[0::2], pares[1::2], strict=True):
        cor = cor_para_esri(cor_bruta, paint.get(_chave_de_cor(tipo)[1], 1.0))
        if cor is None or isinstance(valor, (list, dict)):
            return None
        infos.append({"value": str(valor), "label": str(valor),
                      "symbol": _simbolo(tipo, cor, paint), "description": ""})
    if not infos:
        return None
    padrao = cor_para_esri(expr[-1], paint.get(_chave_de_cor(tipo)[1], 1.0))
    r = {"type": "uniqueValue", "field1": campo, "field2": None, "field3": None,
         "fieldDelimiter": ",", "uniqueValueInfos": infos}
    if padrao is not None:
        r["defaultSymbol"] = _simbolo(tipo, padrao, paint)
        r["defaultLabel"] = "outros"
    return r


def _class_breaks(expr: list, tipo: str, paint: dict) -> dict | None:
    """`["step", ["get", campo], cor0, corte1, cor1, corte2, cor2, ...]`."""
    campo = _campo_de(expr[1] if len(expr) > 1 else None)
    if campo is None or len(expr) < 5 or (len(expr) - 3) % 2 != 0:
        return None
    opacidade = paint.get(_chave_de_cor(tipo)[1], 1.0)
    cores = [expr[2]] + list(expr[4::2])
    cortes = list(expr[3::2])
    if len(cores) != len(cortes) + 1:
        return None
    infos = []
    minimo = None
    for i, cor_bruta in enumerate(cores):
        cor = cor_para_esri(cor_bruta, opacidade)
        if cor is None:
            return None
        maximo = cortes[i] if i < len(cortes) else None
        if not isinstance(maximo, (int, float)) and maximo is not None:
            return None
        infos.append({
            "classMinValue": minimo,
            "classMaxValue": maximo,
            "label": f"{'' if minimo is None else minimo} - {'' if maximo is None else maximo}".strip(),
            "symbol": _simbolo(tipo, cor, paint),
            "description": "",
        })
        minimo = maximo
    return {"type": "classBreaks", "field": campo, "classificationMethod": "esriClassifyManual",
            "minValue": infos[0]["classMaxValue"], "classBreakInfos": infos}
