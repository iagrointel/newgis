"""Leitor do subconjunto SLD 1.0 que o escritor da casa produz (item L2-04-i; par de
`app/estilos/sld.py`, que é só escritor). Serve aos parâmetros `SLD_BODY=` e `SLD=` do WMS: o cliente
manda um estilo e a imagem sai com ELE, sem gravar nada no catálogo.

Subconjunto declarado (o mesmo que o escritor gera, mais o que QGIS/GeoServer emitem para ele):
`NamedLayer/UserStyle/FeatureTypeStyle/Rule` com `PolygonSymbolizer`, `LineSymbolizer`,
`PointSymbolizer` (`Mark/WellKnownName` + `Size`), `Fill`/`Stroke` por `CssParameter`/`SvgParameter`,
e filtro `ogc:PropertyIsEqualTo` / `PropertyIsBetween` / `PropertyIsGreaterThanOrEqualTo` +
`PropertyIsLessThan` dentro de `ogc:And`. O que estiver fora vira aviso e a regra é ignorada — nunca
erro 500, nunca execução de nada.

Segurança: o XML entra por `defusedxml` (a refutação do item manda `SLD_BODY` com entidade externa) e
o documento tem teto de tamanho. Nada de `SLD=` com URL de fora: o parâmetro só aceita endereço do
próprio servidor, pelo mesmo motivo do L0-11 (nenhuma rota busca URL arbitrária da internet).
"""

from __future__ import annotations

from defusedxml import ElementTree as DefusedET

MAX_BYTES = 256 * 1024
_SLD = "{http://www.opengis.net/sld}"
_SE = "{http://www.opengis.net/se}"
_OGC = "{http://www.opengis.net/ogc}"


class SldInvalido(ValueError):
    def __init__(self, mensagem: str, detalhe: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe


def _sem_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _achar(no, nome: str):
    """Filho direto pelo nome local (o SLD real vem ora em `sld:`, ora em `se:`, ora sem prefixo)."""
    for filho in no:
        if _sem_ns(filho.tag) == nome:
            return filho
    return None


def _todos(no, nome: str):
    return [f for f in no.iter() if _sem_ns(f.tag) == nome]


def _parametros(no) -> dict:
    """`CssParameter`/`SvgParameter` -> {nome: valor} (fill, fill-opacity, stroke, stroke-width, ...)."""
    saida = {}
    if no is None:
        return saida
    for f in no:
        if _sem_ns(f.tag) in ("CssParameter", "SvgParameter"):
            nome = f.attrib.get("name") or ""
            if nome:
                saida[nome] = (f.text or "").strip()
    return saida


def _numero(v, padrao=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def _filtro(no) -> list | None:
    """`ogc:Filter` -> expressão no vocabulário do compilador de estilo (a mesma que o pintor avalia)."""
    if no is None:
        return None
    for f in no:
        return _condicao(f)
    return None


def _condicao(no) -> list | None:
    nome = _sem_ns(no.tag)
    if nome == "And":
        partes = [c for c in (_condicao(f) for f in no) if c]
        return ["all", *partes] if partes else None
    if nome == "Or":
        partes = [c for c in (_condicao(f) for f in no) if c]
        return ["any", *partes] if partes else None
    if nome == "PropertyIsEqualTo":
        campo, valor = _campo_e_valor(no)
        return ["==", ["get", campo], valor] if campo is not None else None
    if nome in ("PropertyIsGreaterThanOrEqualTo", "PropertyIsGreaterThan",
                "PropertyIsLessThanOrEqualTo", "PropertyIsLessThan"):
        campo, valor = _campo_e_valor(no)
        op = {"PropertyIsGreaterThanOrEqualTo": ">=", "PropertyIsGreaterThan": ">",
              "PropertyIsLessThanOrEqualTo": "<=", "PropertyIsLessThan": "<"}[nome]
        n = _numero(valor)
        return [op, ["to-number", ["get", campo]], n] if campo is not None and n is not None else None
    if nome == "PropertyIsBetween":
        campo = None
        prop = _achar(no, "PropertyName")
        if prop is not None:
            campo = (prop.text or "").strip()
        menor = _achar(no, "LowerBoundary")
        maior = _achar(no, "UpperBoundary")
        mn = _numero(_texto_literal(menor))
        mx = _numero(_texto_literal(maior))
        if campo and mn is not None and mx is not None:
            return ["all", [">=", ["to-number", ["get", campo]], mn], ["<=", ["to-number", ["get", campo]], mx]]
    return None


def _texto_literal(no):
    """Texto do <Literal> dentro de <LowerBoundary>/<UpperBoundary> (ou None)."""
    if no is None:
        return None
    lit = _achar(no, "Literal")
    return None if lit is None else (lit.text or "").strip()


def _campo_e_valor(no):
    campo = valor = None
    for f in no:
        n = _sem_ns(f.tag)
        if n == "PropertyName":
            campo = (f.text or "").strip()
        elif n == "Literal":
            valor = (f.text or "").strip()
    return campo, valor


def ler(xml: str | bytes) -> dict:
    """SLD -> `{'geometria', 'classes': [{'rotulo','cor','teste'}], 'simbolo': {...}}` — exatamente o
    que `app/ogc_mapas/pintor.pintar` consome. Levanta `SldInvalido` para XML malformado, documento
    grande demais ou sem nenhuma regra reconhecida."""
    bruto = xml.encode("utf-8") if isinstance(xml, str) else xml
    if len(bruto) > MAX_BYTES:
        raise SldInvalido(f"SLD acima do teto de {MAX_BYTES} bytes")
    try:
        # defusedxml recusa entidade externa, DTD remoto e bomba de entidade (refutação do item)
        raiz = DefusedET.fromstring(bruto, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as e:  # noqa: BLE001 - qualquer falha de análise vira 400 do protocolo, nunca 500
        raise SldInvalido("SLD não pôde ser lido", str(e)[:200]) from e
    regras = _todos(raiz, "Rule")
    if not regras:
        raise SldInvalido("SLD sem nenhuma <Rule>")
    classes: list[dict] = []
    simbolo: dict = {}
    geometria = None
    avisos: list[str] = []
    for regra in regras:
        # `or` não serve aqui: um Element sem filhos é FALSO em ElementTree, e <Name> não tem filhos
        nome_no = _achar(regra, "Name")
        if nome_no is None:
            nome_no = _achar(regra, "Title")
        rotulo = (nome_no.text or "").strip() if nome_no is not None else ""
        teste = _filtro(_achar(regra, "Filter"))
        cor = None
        for simb in regra:
            tipo = _sem_ns(simb.tag)
            if tipo == "PolygonSymbolizer":
                geometria = geometria or "poligono"
                p = _parametros(_achar(simb, "Fill"))
                t = _parametros(_achar(simb, "Stroke"))
                cor = p.get("fill") or cor
                simbolo.setdefault("opacidade", _numero(p.get("fill-opacity"), 0.85))
                if t.get("stroke"):
                    simbolo.setdefault("contorno_cor", t["stroke"])
                    simbolo.setdefault("contorno_largura", _numero(t.get("stroke-width"), 1.0))
            elif tipo == "LineSymbolizer":
                geometria = geometria or "linha"
                t = _parametros(_achar(simb, "Stroke"))
                cor = t.get("stroke") or cor
                simbolo.setdefault("largura", _numero(t.get("stroke-width"), 1.0))
                simbolo.setdefault("opacidade", _numero(t.get("stroke-opacity"), 1.0))
            elif tipo == "PointSymbolizer":
                geometria = geometria or "ponto"
                grafico = _achar(simb, "Graphic")
                if grafico is not None:
                    marca = _achar(grafico, "Mark")
                    if marca is not None:
                        p = _parametros(_achar(marca, "Fill"))
                        cor = p.get("fill") or cor
                        t = _parametros(_achar(marca, "Stroke"))
                        if t.get("stroke"):
                            simbolo.setdefault("contorno_cor", t["stroke"])
                    tam = _achar(grafico, "Size")
                    if tam is not None:
                        simbolo.setdefault("raio", (_numero((tam.text or "").strip(), 8.0) or 8.0) / 2)
            elif tipo in ("TextSymbolizer", "RasterSymbolizer"):
                avisos.append(f"{tipo} ignorado (fora do subconjunto)")
        if cor:
            classes.append({"rotulo": rotulo or cor, "cor": cor, "teste": teste})
    if not classes:
        raise SldInvalido("SLD sem símbolo reconhecido (Polygon/Line/PointSymbolizer com Fill ou Stroke)")
    # regra sem filtro é a padrão e tem de ser a ÚLTIMA (o pintor devolve a primeira que casa)
    classes.sort(key=lambda c: c["teste"] is None)
    # semântica do SLD: feição que não casa com nenhuma regra NÃO é desenhada (diferente do `case` do
    # MapLibre, onde a última classe é o padrão) — por isso `padrao` só vale se houver regra sem filtro
    padrao = any(c["teste"] is None for c in classes)
    return {"geometria": geometria or "poligono", "classes": classes, "simbolo": simbolo,
            "padrao": padrao, "avisos": avisos}
