"""SVG só depois de sanitizado (item L7-03-a-antivirus-upload; docs/SEGURANCA.md §9). Um SVG é um documento XML
que o navegador executa: `<script>`, manipuladores `on*`, `<foreignObject>` (HTML dentro do SVG), `href`/
`xlink:href` com `javascript:`/`data:` e `<use>` para fora do arquivo são vetores de script. A regra é lista
BRANCA de elementos e atributos (o que não está na lista some), nunca lista negra: um atributo novo do navegador
não pode virar buraco. Parse por `defusedxml` (nunca resolve entidade externa nem expande bomba de entidades) —
mesma escolha de `app/conexao/csw.py` e `proveniencia.py`. Devolve os bytes do SVG reconstruído (sem DOCTYPE,
sem instrução de processamento, sem comentário)."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET  # só para escrever; o parse é sempre defusedxml
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET_seguro
from defusedxml import DefusedXmlException

NS_SVG = "http://www.w3.org/2000/svg"
NS_XLINK = "http://www.w3.org/1999/xlink"
ELEMENTOS = frozenset({
    "svg", "g", "defs", "symbol", "use", "title", "desc", "metadata", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "textPath", "image", "clipPath", "mask", "pattern", "marker",
    "linearGradient", "radialGradient", "stop", "filter", "feBlend", "feColorMatrix", "feComponentTransfer",
    "feComposite", "feConvolveMatrix", "feDiffuseLighting", "feDisplacementMap", "feFlood", "feGaussianBlur",
    "feImage", "feMerge", "feMergeNode", "feMorphology", "feOffset", "feSpecularLighting", "feTile", "feTurbulence",
    "feFuncR", "feFuncG", "feFuncB", "feFuncA", "feDistantLight", "fePointLight", "feSpotLight", "switch", "view",
})
ATRIBUTOS_URL = frozenset({"href", "xlink:href"})
_RE_URL_PERIGOSA = re.compile(r"^\s*(javascript|data|vbscript|file|ftp|https?):", re.I)
_RE_URL_EM_CSS = re.compile(r"url\s*\(", re.I)


class SVGInvalido(ValueError):
    """não é um SVG analisável (XML inválido, entidade externa, raiz que não é <svg>)."""


def _local(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, nome = tag[1:].split("}", 1)
        return ns, nome
    return None, tag


def _atributo_ok(nome: str, valor: str) -> bool:
    base = nome.split("}", 1)[-1] if nome.startswith("{") else nome
    if base.lower().startswith("on"):
        return False  # onload, onclick, on*: manipuladores de evento
    if base in ("href", "xlink:href") or nome == f"{{{NS_XLINK}}}href":
        v = valor.strip()
        # só referência interna (#id) ou imagem embutida raster (data:image/png|jpeg|gif|webp)
        if v.startswith("#"):
            return True
        return bool(re.match(r"^data:image/(png|jpe?g|gif|webp);base64,", v, re.I))
    if base == "style" and _RE_URL_EM_CSS.search(valor):
        return False  # url() em style carrega recurso externo/script via CSS
    if _RE_URL_PERIGOSA.match(valor) and base not in ("xmlns", "xmlns:xlink"):
        return False
    return True


def _limpar(el) -> None:
    for filho in list(el):
        ns, nome = _local(filho.tag)
        if (ns not in (None, NS_SVG)) or nome not in ELEMENTOS:
            el.remove(filho)  # script, foreignObject, animate*, set, a, iframe, qualquer namespace estranho
            continue
        for k in list(filho.attrib):
            if not _atributo_ok(k, filho.attrib[k]):
                del filho.attrib[k]
        _limpar(filho)


def sanitizar(bruto: bytes) -> bytes:
    try:
        raiz = ET_seguro.fromstring(bruto)
    except DefusedXmlException as e:
        raise SVGInvalido(f"svg com construção proibida: {type(e).__name__}") from e
    except (ParseError, ValueError) as e:
        raise SVGInvalido(f"svg inválido: {str(e)[:120]}") from e
    ns, nome = _local(raiz.tag)
    if nome != "svg" or ns not in (None, NS_SVG):
        raise SVGInvalido("raiz não é <svg>")
    for k in list(raiz.attrib):
        if not _atributo_ok(k, raiz.attrib[k]):
            del raiz.attrib[k]
    _limpar(raiz)
    ET.register_namespace("", NS_SVG)
    ET.register_namespace("xlink", NS_XLINK)
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=False)


def tem_script(dados: bytes) -> bool:
    """checagem barata para teste/auditoria: qualquer marca de script sobreviveu?"""
    baixo = dados.lower()
    marcas = (b"<script", b"javascript:", b"<foreignobject", b"onload=", b"onclick=", b"onerror=")
    return any(m in baixo for m in marcas)
