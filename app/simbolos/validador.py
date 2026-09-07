"""Saneamento do SVG enviado pelo inquilino (item L2-02-e-simbolos-sprites-glifos; refutação exigida:
bomba de XML e nome de ícone padrão colidindo). Recurso nativo: `defusedxml` (dependência já instalada,
puxada pelo `cairosvg` — ver `requirements.txt`) recusa DOCTYPE/ENTITY, a própria classe de ataque da
"bomba de bilhões de risos" (entidade que se expande exponencialmente a partir de um arquivo minúsculo).
O teto de 64 kB de arquivo por si só barra o "bilhões de elementos" literais (não cabem em 64 kB de texto);
o `<use>` recursivo (outro jeito de amplificar poucos bytes em muita geometria) é recusado por completo:
não é preciso para um pictograma de sprite autocontido, então não precisa suportar (Ponytail: reduzir)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as DET
from defusedxml.common import DefusedXmlException

TAMANHO_MAXIMO_BYTES = 64 * 1024
MAX_ELEMENTOS = 2000
MAX_PROFUNDIDADE = 40
NOME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

TAGS_PROIBIDAS = {
    "script", "foreignobject", "iframe", "object", "embed", "video", "audio",
    "animate", "animatetransform", "animatemotion", "set", "handler", "listener",
    "use",  # amplificação recursiva de geometria — não suportado (ver docstring)
}
# atributo de evento (onload, onclick, ...) ou referência externa (href/xlink:href que não seja "#algo")
ATRIBUTO_EVENTO = re.compile(r"^on[a-z]+$", re.IGNORECASE)
HREF_LOCAL = re.compile(r"^#")


@dataclass(frozen=True)
class SvgRecusado(Exception):
    motivo: str
    detalhe: str

    def __str__(self) -> str:  # pragma: no cover - só para log
        return f"{self.motivo}: {self.detalhe}"


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def validar_nome(nome: str) -> str:
    nome = (nome or "").strip().lower()
    if not NOME_PATTERN.match(nome):
        raise SvgRecusado("nome_invalido", "nome do ícone: minúsculas, dígitos e hífen, até 64 caracteres")
    return nome


def sanear_svg(conteudo: bytes) -> str:
    """Levanta `SvgRecusado` (a rota traduz para 422) se o SVG não for seguro para compor no sprite.
    Devolve o texto (decodificado utf-8) já validado, sem modificar a geometria."""
    if len(conteudo) == 0:
        raise SvgRecusado("vazio", "arquivo vazio")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise SvgRecusado("tamanho", f"máximo {TAMANHO_MAXIMO_BYTES} bytes, recebido {len(conteudo)}")
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SvgRecusado("codificacao", "não é UTF-8 válido") from e
    try:
        raiz = DET.fromstring(conteudo, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as e:
        # é exatamente a classe de ataque da refutação: DOCTYPE/ENTITY (bomba de expansão) ou referência externa
        raise SvgRecusado("xml_perigoso", f"DOCTYPE/ENTITY/referência externa recusados ({type(e).__name__})") from e
    except ParseError as e:
        raise SvgRecusado("xml_invalido", str(e)) from e

    if _localname(raiz.tag) != "svg":
        raise SvgRecusado("raiz_invalida", "elemento raiz precisa ser <svg>")

    contagem = 0
    for elemento in raiz.iter():
        contagem += 1
        if contagem > MAX_ELEMENTOS:
            raise SvgRecusado("elementos_demais", f"mais de {MAX_ELEMENTOS} elementos (proteção contra bomba)")
        tag = _localname(elemento.tag)
        if tag in TAGS_PROIBIDAS:
            raise SvgRecusado("tag_proibida", f"elemento <{tag}> não é permitido")
        for chave, valor in elemento.attrib.items():
            nome_attr = _localname(chave)
            if ATRIBUTO_EVENTO.match(nome_attr):
                raise SvgRecusado("atributo_evento", f"atributo de evento não permitido: {nome_attr}")
            if nome_attr in ("href",) and not HREF_LOCAL.match(valor or ""):
                raise SvgRecusado("referencia_externa", f"href externo não permitido: {valor[:80]!r}")
            if valor and valor.strip().lower().startswith(("javascript:", "data:text/html")):
                raise SvgRecusado("referencia_externa", "valor com esquema perigoso")

    _profundidade_maxima(raiz, 0)
    return texto


def _profundidade_maxima(elemento, prof: int) -> None:
    if prof > MAX_PROFUNDIDADE:
        raise SvgRecusado("profundidade_demais", f"mais de {MAX_PROFUNDIDADE} níveis de aninhamento")
    for filho in elemento:
        _profundidade_maxima(filho, prof + 1)
