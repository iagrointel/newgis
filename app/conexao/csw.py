"""Descoberta por catálogo CSW 2.0.2 de terceiros (item L6-06-descoberta-csw). A INDE (Infraestrutura Nacional de
Dados Espaciais) e geoportais de órgãos publicam catálogos CSW (GeoNetwork, pycsw) com registros ISO 19139;
este módulo monta o pedido `GetRecords`/`GetRecordById` por KVP (GET — o mesmo caminho de `buscar_seguro`, sem
cliente HTTP à parte e sem POST de XML), lê o registro `gmd:MD_Metadata` com defusedxml e devolve o que o
registro DECLARA: título, resumo, organização, datas, licença, extensão e os serviços ligados (`CI_OnlineResource`
com protocolo `OGC:WMS`/`OGC:WFS`/`OGC:WMTS` E endereço). Registro com protocolo declarado mas `linkage` vazio
NÃO é serviço (caso real na INDE: cartas do IBGE com `OGC:WMS-1.1.1-http-get-map` e URL em branco) — vira aviso.

Regra da casa (ADR 0012, "procedência errada é pior que nenhuma"): todo campo da ficha vem do registro ou fica
`None`; o código de restrição (`MD_RestrictionCode`) NUNCA é lido como licença — só texto de `otherConstraints`/
`useLimitation` é licença declarada. Medido em 07/09/2026 contra o CSW da INDE: `GetRecords` por GET com
`CONSTRAINTLANGUAGE=CQL_TEXT` e `outputSchema=gmd` responde 200 (10.134 registros para 'hidrografia', 394 com
BBOX de São Paulo); `GetRecordById` com `elementSetName=full` devolve o `gmd:MD_Metadata` inteiro."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError  # só o TIPO; o parse é sempre via defusedxml

import defusedxml.ElementTree as ET_seguro
from defusedxml import DefusedXmlException

from app import limites

NS_CSW = "http://www.opengis.net/cat/csw/2.0.2"
NS_GMD = "http://www.isotc211.org/2005/gmd"
NS_OWS = "http://www.opengis.net/ows"
ISO_GMD = NS_GMD  # valor de `outputSchema` que pede ISO 19139
# protocolos que viram conexão (ordem = prioridade de exibição); comparação por substring em maiúsculas cobre as
# grafias do GeoNetwork ("OGC:WMS", "OGC:WMS-1.1.1-http-get-map", "OGC:WFS-2.0.0-http-get-capabilities")
_PROTOCOLO_TIPO = (("OGC:WMTS", "wmts"), ("OGC:WMS", "wms"), ("OGC:WFS", "wfs"))
_SERVICO_QUERY = {"WMS": "wms", "WFS": "wfs", "WMTS": "wmts"}
_PARAMS_CAMADA = ("layers", "layer", "typename", "typenames")


class ErroCSW(ValueError):
    """resposta que não é um CSW 2.0.2 utilizável (XML inválido, entidade externa, ExceptionReport, sem raiz csw)."""

    def __init__(self, motivo: str, detalhe: str | None = None):
        super().__init__(motivo)
        self.motivo = motivo
        self.detalhe = detalhe


@dataclass(frozen=True)
class Servico:
    tipo: str            # wms | wfs | wmts (o mesmo vocabulário de limites.CONEXAO_TIPOS)
    url: str             # endereço BASE do serviço (sem querystring) — o que vai para plat.conexao.url
    camada: str | None   # nome da camada/tipo de feição declarado (gmd:name ou layers=/typeName= da URL)
    url_declarada: str   # o linkage como veio no registro (fica na ficha, nunca é perdido)
    protocolo: str       # texto do gmd:protocol como veio


@dataclass
class Registro:
    identificador: str | None
    titulo: str | None
    resumo: str | None
    organizacao: str | None
    data_do_dado: str | None       # CI_Date de creation/publication/revision (nessa ordem de preferência)
    data_metadado: str | None      # gmd:dateStamp
    palavras_chave: list[str]
    bbox: list[float] | None       # [oeste, sul, leste, norte] em graus (EX_GeographicBoundingBox)
    licenca: str | None            # otherConstraints / useLimitation (texto declarado), nunca um código
    restricoes: list[str]          # códigos MD_RestrictionCode declarados (informativo)
    linhagem: str | None           # LI_Lineage/statement
    frequencia: str | None         # MD_MaintenanceFrequencyCode
    servicos: list[Servico] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def sem_servico(self) -> bool:
        return not self.servicos


@dataclass
class ResultadoBusca:
    total: int
    devolvidos: int
    proximo: int | None      # nextRecord (0 = não há mais) -> None quando acabou
    registros: list[Registro]


# --------------------------------------------------------------------------- pedidos (KVP por GET)


def _base(url: str) -> tuple[str, list[tuple[str, str]]]:
    """separa a URL do catálogo dos parâmetros que o usuário já colou (mantidos, exceto os do CSW que montamos)."""
    p = urlsplit(url)
    fixos = [
        (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in {
            "service", "version", "request", "typenames", "resulttype", "elementsetname", "outputschema",
            "constraintlanguage", "constraint_language_version", "constraint", "maxrecords", "startposition", "id",
        }
    ]
    return urlunsplit((p.scheme, p.netloc, p.path, "", "")), fixos


def _cql_texto(texto: str) -> str:
    """AnyText like '%<texto>%' — aspa simples do CQL dobrada, o resto o urlencode protege."""
    return texto.replace("'", "''")


def url_getrecords(
    url_csw: str, texto: str | None, bbox: list[float] | None, inicio: int = 1, maximo: int | None = None,
) -> str:
    maximo = min(maximo or limites.CSW_MAX_REGISTROS, limites.CSW_MAX_REGISTROS)
    partes = []
    if texto and texto.strip():
        partes.append(f"AnyText like '%{_cql_texto(' '.join(texto.split()))}%'")
    if bbox:
        oeste, sul, leste, norte = bbox
        partes.append(f"BBOX(ows:BoundingBox,{oeste:g},{sul:g},{leste:g},{norte:g})")
    base, fixos = _base(url_csw)
    params = fixos + [
        ("service", "CSW"), ("version", "2.0.2"), ("request", "GetRecords"), ("typeNames", "csw:Record"),
        ("resultType", "results"), ("elementSetName", "full"), ("outputSchema", ISO_GMD),
        ("maxRecords", str(maximo)), ("startPosition", str(max(1, inicio))),
    ]
    if partes:
        params += [
            ("constraintLanguage", "CQL_TEXT"), ("constraint_language_version", "1.1.0"),
            ("constraint", " AND ".join(partes)),
        ]
    return f"{base}?{urlencode(params)}"


def url_getrecordbyid(url_csw: str, identificador: str) -> str:
    base, fixos = _base(url_csw)
    params = fixos + [
        ("service", "CSW"), ("version", "2.0.2"), ("request", "GetRecordById"), ("id", identificador),
        ("outputSchema", ISO_GMD), ("elementSetName", "full"),
    ]
    return f"{base}?{urlencode(params)}"


# --------------------------------------------------------------------------- leitura do XML


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _texto(el) -> str | None:
    """texto de um elemento gmd (gco:CharacterString, gco:Date, gmx:Anchor... — qualquer folha de texto)."""
    if el is None:
        return None
    s = " ".join("".join(el.itertext()).split())
    return s or None


def _filho(el, *caminho: str):
    """desce por nomes locais (sem namespace): _filho(md, 'fileIdentifier') -> primeiro filho com esse nome."""
    atual = el
    for nome in caminho:
        if atual is None:
            return None
        atual = next((c for c in atual if _local(c.tag) == nome), None)
    return atual


def _todos(el, nome: str):
    return [c for c in el.iter() if _local(c.tag) == nome]


def _raiz(corpo: bytes):
    try:
        return ET_seguro.fromstring(corpo)  # nunca resolve entidade externa nem expande bomba (defusedxml)
    except DefusedXmlException as e:
        raise ErroCSW("xml_inseguro", type(e).__name__) from e
    except (ParseError, ValueError) as e:
        raise ErroCSW("xml_invalido", str(e)[:200]) from e


def _excecao(raiz) -> str | None:
    if _local(raiz.tag) == "ExceptionReport":
        textos = [t for t in (_texto(e) for e in _todos(raiz, "ExceptionText")) if t]
        codigo = next((e.get("exceptionCode") for e in _todos(raiz, "Exception")), None)
        return f"{codigo or 'Exception'}: {'; '.join(textos)[:300]}" if (codigo or textos) else "ExceptionReport"
    return None


def _camada_da_url(url: str) -> str | None:
    for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=False):
        if k.lower() in _PARAMS_CAMADA and v.strip():
            return v.strip()
    return None


def _tipo_do_protocolo(protocolo: str | None, url: str) -> str | None:
    p = (protocolo or "").upper()
    for marca, tipo in _PROTOCOLO_TIPO:
        if marca in p:
            return tipo
    # sem protocolo declarado: só quando a própria URL diz explicitamente `service=WMS|WFS|WMTS`
    for k, v in parse_qsl(urlsplit(url).query):
        if k.lower() == "service" and v.upper() in _SERVICO_QUERY:
            return _SERVICO_QUERY[v.upper()]
    return None


def _servicos(md, avisos: list[str]) -> list[Servico]:
    saida: list[Servico] = []
    vistos: set[tuple[str, str, str | None]] = set()
    for onl in _todos(md, "CI_OnlineResource"):
        protocolo = _texto(_filho(onl, "protocol"))
        url = _texto(_filho(onl, "linkage")) or ""
        tipo = _tipo_do_protocolo(protocolo, url)
        if tipo is None:
            continue  # download, página, e-mail: não é serviço de mapa
        if not url.lower().startswith(("http://", "https://")):
            avisos.append(f"OnlineResource {protocolo or tipo} sem endereço utilizável ({url or 'vazio'})")
            continue
        p = urlsplit(url)
        base = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
        camada = _texto(_filho(onl, "name")) or _camada_da_url(url)
        chave = (tipo, base, camada)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(Servico(tipo=tipo, url=base, camada=camada, url_declarada=url, protocolo=protocolo or ""))
    return saida


def _data_do_dado(md) -> str | None:
    """CI_Date do recurso: creation > publication > revision; o valor pode vir em gco:Date, gco:DateTime ou até
    gco:CharacterString (registros antigos da INDE) — lê-se o texto, não o tipo."""
    por_tipo: dict[str, str] = {}
    ident = _filho(md, "identificationInfo")
    for d in _todos(ident if ident is not None else md, "CI_Date"):
        tipo_el = _filho(d, "dateType", "CI_DateTypeCode")
        tipo = (tipo_el.get("codeListValue") if tipo_el is not None else None) or (_texto(tipo_el) or "")
        valor = _texto(_filho(d, "date"))
        if valor and tipo not in por_tipo:
            por_tipo[tipo] = valor
    for tipo in ("creation", "publication", "revision"):
        if tipo in por_tipo:
            return por_tipo[tipo]
    return next(iter(por_tipo.values()), None)


def _bbox(md) -> list[float] | None:
    b = next(iter(_todos(md, "EX_GeographicBoundingBox")), None)
    if b is None:
        return None
    try:
        valores = [
            float(_texto(_filho(b, k)) or "x")
            for k in ("westBoundLongitude", "southBoundLatitude", "eastBoundLongitude", "northBoundLatitude")
        ]
    except ValueError:
        return None
    oeste, sul, leste, norte = valores
    if not (-180 <= oeste <= 180 and -180 <= leste <= 180 and -90 <= sul <= 90 and -90 <= norte <= 90
            and oeste <= leste and sul <= norte):
        return None
    return valores


def _licenca(md) -> tuple[str | None, list[str]]:
    textos, codigos = [], []
    for tag in ("otherConstraints", "useLimitation"):
        for e in _todos(md, tag):
            t = _texto(e)
            if t and t not in textos:
                textos.append(t)
    for e in _todos(md, "MD_RestrictionCode"):
        c = e.get("codeListValue") or _texto(e)
        if c and c not in codigos:
            codigos.append(c)
    return ("; ".join(textos)[:limites.CSW_TEXTO_MAX] if textos else None), codigos


def analisar_registro(md) -> Registro:
    """`md` é um elemento `gmd:MD_Metadata` (ou `csw:Record`/`gmd:*` equivalente: só nomes locais importam)."""
    avisos: list[str] = []
    ident = _filho(md, "identificationInfo")
    citacao = next(iter(_todos(ident, "CI_Citation")), None) if ident is not None else None
    titulo = _texto(_filho(citacao, "title")) if citacao is not None else None
    resumo = _texto(_filho(ident, "MD_DataIdentification", "abstract")) if ident is not None else None
    if resumo is None and ident is not None:
        resumo = next((t for t in (_texto(e) for e in _todos(ident, "abstract")) if t), None)
    org = None
    if ident is not None:
        org = next((t for t in (_texto(e) for e in _todos(ident, "organisationName")) if t), None)
    if org is None:
        org = next((t for t in (_texto(e) for e in _todos(md, "organisationName")) if t), None)
    palavras = []
    for e in _todos(md, "keyword"):
        t = _texto(e)
        if t and t not in palavras:
            palavras.append(t)
    licenca, restricoes = _licenca(md)
    freq = next(iter(_todos(md, "MD_MaintenanceFrequencyCode")), None)
    servicos = _servicos(md, avisos)
    if not servicos:
        avisos.append("registro sem serviço ligado (nenhum OnlineResource WMS/WFS/WMTS com endereço)")
    if licenca is None:
        avisos.append("registro não declara licença em texto (otherConstraints/useLimitation ausentes)")
    return Registro(
        identificador=_texto(_filho(md, "fileIdentifier")),
        titulo=titulo,
        resumo=(resumo or "")[: limites.CSW_TEXTO_MAX] or None,
        organizacao=org,
        data_do_dado=_data_do_dado(md),
        data_metadado=_texto(_filho(md, "dateStamp")),
        palavras_chave=palavras[:limites.CSW_PALAVRAS_MAX],
        bbox=_bbox(md),
        licenca=licenca,
        restricoes=restricoes,
        linhagem=(next((t for t in (_texto(e) for e in _todos(md, "statement")) if t), None) or "")[
            : limites.CSW_TEXTO_MAX
        ] or None,
        frequencia=(freq.get("codeListValue") or _texto(freq)) if freq is not None else None,
        servicos=servicos,
        avisos=avisos,
    )


def _registros_da_raiz(raiz) -> list:
    """os `gmd:MD_Metadata` (ISO) ou, se o catálogo ignorou o outputSchema, os `csw:Record` (Dublin Core: sem
    OnlineResource — viram registros sem serviço, com aviso)."""
    mds = _todos(raiz, "MD_Metadata")
    return mds or _todos(raiz, "Record")


def analisar_getrecords(corpo: bytes) -> ResultadoBusca:
    raiz = _raiz(corpo)
    exc = _excecao(raiz)
    if exc:
        raise ErroCSW("excecao_do_catalogo", exc)
    if _local(raiz.tag) != "GetRecordsResponse":
        raise ErroCSW("resposta_nao_e_csw", f"raiz {_local(raiz.tag)!r}")
    res = _filho(raiz, "SearchResults")
    if res is None:
        raise ErroCSW("resposta_nao_e_csw", "sem csw:SearchResults")
    registros = [analisar_registro(md) for md in _registros_da_raiz(res)]

    def _int(nome: str, padrao: int) -> int:
        try:
            return int(res.get(nome) or padrao)
        except ValueError:
            return padrao

    proximo = _int("nextRecord", 0)
    return ResultadoBusca(
        total=_int("numberOfRecordsMatched", len(registros)),
        devolvidos=_int("numberOfRecordsReturned", len(registros)),
        proximo=proximo if proximo > 0 else None,
        registros=registros,
    )


def analisar_getrecordbyid(corpo: bytes) -> Registro | None:
    raiz = _raiz(corpo)
    exc = _excecao(raiz)
    if exc:
        raise ErroCSW("excecao_do_catalogo", exc)
    if _local(raiz.tag) == "MD_Metadata":  # alguns catálogos devolvem o registro sem o envelope
        return analisar_registro(raiz)
    if _local(raiz.tag) != "GetRecordByIdResponse":
        raise ErroCSW("resposta_nao_e_csw", f"raiz {_local(raiz.tag)!r}")
    mds = _registros_da_raiz(raiz)
    return analisar_registro(mds[0]) if mds else None


# --------------------------------------------------------------------------- ficha


def ficha(registro: Registro, servico: Servico, url_csw: str, corpo: bytes, data_de_acesso: str) -> dict:
    """Os 10 campos de `dados.procedencia` (ADR 0012 / decisão B11) preenchidos do registro ISO, mais o que o
    registro traz e a ficha genérica não tem (título, resumo, palavras-chave, extensão, catálogo de origem).
    Campo não declarado fica `None` — a tela mostra "não registrado"."""
    if registro.frequencia:
        frescor = f"frequência de manutenção declarada no registro ISO: {registro.frequencia}"
    elif registro.data_metadado:
        frescor = f"registro ISO datado de {registro.data_metadado}; frequência de manutenção não declarada"
    else:
        frescor = None
    comando = f"GET {url_getrecordbyid(url_csw, registro.identificador)}" if registro.identificador else None
    return {
        "fonte": registro.organizacao or registro.titulo,
        "url": servico.url,
        "licenca": registro.licenca,
        "data_do_dado": registro.data_do_dado,
        "data_de_acesso": data_de_acesso,
        "metodo": (
            f"registro ISO 19139 lido do catálogo CSW 2.0.2 ({url_csw}), GetRecordById "
            f"{registro.identificador or '?'}; serviço {servico.tipo.upper()} declarado em CI_OnlineResource "
            f"({servico.protocolo or 'sem protocolo, service= na URL'})"
        ),
        "confianca": "declarado" if (registro.licenca or registro.organizacao) else None,
        "frescor": frescor,
        "sha256": hashlib.sha256(corpo).hexdigest() if corpo else None,
        "comando_reexecucao": comando,
        "limites": registro.avisos or None,
        "responsavel": registro.organizacao,
        "titulo": registro.titulo,
        "resumo": registro.resumo,
        "palavras_chave": registro.palavras_chave,
        "bbox": registro.bbox,
        "restricoes": registro.restricoes,
        "linhagem": registro.linhagem,
        "catalogo": {"url": url_csw, "identificador": registro.identificador, "data_metadado": registro.data_metadado},
        "url_declarada": servico.url_declarada,
    }


def registro_json(r: Registro) -> dict:
    return {
        "identificador": r.identificador,
        "titulo": r.titulo,
        "resumo": r.resumo,
        "organizacao": r.organizacao,
        "data_do_dado": r.data_do_dado,
        "data_metadado": r.data_metadado,
        "palavras_chave": r.palavras_chave,
        "bbox": r.bbox,
        "licenca": r.licenca,
        "restricoes": r.restricoes,
        "frequencia": r.frequencia,
        "servicos": [
            {
                "tipo": s.tipo, "url": s.url, "camada": s.camada, "url_declarada": s.url_declarada,
                "protocolo": s.protocolo,
            }
            for s in r.servicos
        ],
        "sem_servico": r.sem_servico,
        "avisos": r.avisos,
    }
