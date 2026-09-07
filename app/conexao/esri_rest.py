"""Conector ArcGIS REST externo (item L6-02-d-arcgis-rest-externo; ADR 0020) — leitura de Portal e AGOL
públicos de terceiro. Só o modo REFERENCIADO (ao vivo) está coberto aqui; o modo copiado (materializar em
PostGIS) fica de fora deste turno, nomeado no handoff, mesmo padrão do L6-02-b (WMS/WMTS).

Três capacidades, todas sobre `app.conexao.seguranca.buscar_seguro` (nunca um cliente HTTP à parte, então a
defesa contra SSRF/rebinding do item L6-02-a cobre cada chamada):

  FeatureServer  — `descrever_camada` lê o layer (`?f=json`: geometryType, maxRecordCount, drawingInfo,
                   campos); `contar` usa `returnCountOnly=true` (nunca conta baixando as feições);
                   `consultar_tudo` pagina por `resultOffset`/`resultRecordCount`, SEMPRE clampado ao
                   `maxRecordCount` declarado (ou ao padrão da casa quando o serviço não declara), com teto
                   de páginas e de feições totais — um serviço com `maxRecordCount=1` pára no teto de
                   páginas, nunca em loop infinito, e o corte vira aviso, não erro.
  MapServer      — `exportar_mapa` propõe `/export` (imagem dinâmica renderizada pelo servidor, mesma ideia
                   do GetMap do WMS): bbox, tamanho e SR de saída.
  ImageServer    — `exportar_imagem_raster` propõe `/exportImage`: mesma forma, endpoint diferente.

Simbologia: `simbologia_simples` só lê renderer `type=simple` com símbolo `esriSFS` (polígono) ou `esriSLS`
(linha) — a hipótese do item é "simbologia simples", não o motor de renderização completo do ArcGIS
(classBreaks/uniqueValue ficam fora, sem fingir). `esriPMS`/`esriSMS` (marcador de imagem/pontual) não têm
cor de preenchimento/contorno no sentido do portão e voltam `None`.

Credencial: todo `token` (convenção clássica do ArcGIS Server: parâmetro de querystring, não cabeçalho
Authorization — diferente do Bearer usado pelo teste de saúde genérico) é decifrado em memória pela rota,
passado aqui como argumento, e só é acrescentado à URL FINAL da requisição contra o serviço externo — nunca
entra em `mensagem`/exceção nem é logado (`app/log.py` não recebe este módulo)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from urllib.parse import urlencode

from app import limites
from app.conexao import seguranca

_TIPOS_SIMBOLO_POLIGONO = ("esriSFS",)
_TIPOS_SIMBOLO_LINHA = ("esriSLS",)


class ErroConector(Exception):
    """Erro de leitura do serviço ArcGIS REST — nunca carrega token nem cabeçalho, só a URL pública e o motivo."""


def _com_parametros(url: str, parametros: dict) -> str:
    parametros = {k: v for k, v in parametros.items() if v is not None}
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}{urlencode(parametros)}" if parametros else url


def _url_com_token(url: str, token: str | None) -> str:
    return _com_parametros(url, {"token": token}) if token else url


def _buscar_json(url: str, token: str | None, *, timeout_s: float, max_bytes: int) -> dict:
    """Acrescenta sempre `f=json` (a raiz de um FeatureServer/MapServer sem esse parâmetro devolve a página
    HTML do diretório de serviços do ArcGIS Server, nunca o JSON — achado ao testar contra o SIGEL/ANEEL real,
    07/09/2026) e só então, por cima, o `token` quando houver."""
    alvo = _url_com_token(_com_parametros(url, {"f": "json"}) if "f=json" not in url.lower() else url, token)
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=timeout_s,
        max_bytes=max_bytes, guardar_corpo=True,
    )
    if not r.ok:
        raise ErroConector(f"{url}: {r.mensagem}")
    try:
        doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErroConector(f"{url}: resposta não é JSON válido") from e
    if not isinstance(doc, dict):
        raise ErroConector(f"{url}: resposta JSON não é um objeto")
    if "error" in doc:
        erro = doc["error"] or {}
        codigo = erro.get("code")
        mensagem = erro.get("message") or "erro do serviço ArcGIS"
        if codigo == 499 or "token" in str(mensagem).lower():
            raise ErroConector(f"{url}: serviço exige token ({mensagem!r}) — forneça a credencial da conexão")
        raise ErroConector(f"{url}: {mensagem} (código {codigo})")
    return doc


# ------------------------------------------------------------------ descrição do serviço/camada


@dataclass(frozen=True)
class Simbologia:
    geometria: str  # "poligono" | "linha"
    preenchimento_rgba: tuple[int, int, int, int] | None
    contorno_rgba: tuple[int, int, int, int] | None
    contorno_largura: float | None


def _cor(valor) -> tuple[int, int, int, int] | None:
    if not isinstance(valor, list) or len(valor) != 4:
        return None
    try:
        return tuple(int(c) for c in valor)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def simbologia_simples(drawing_info: dict | None) -> Simbologia | None:
    """`drawingInfo.renderer` do `?f=json` da camada. Só `type=simple`; classBreaks/uniqueValue e símbolo de
    marcador de imagem (`esriPMS`) voltam `None` — nunca inventa uma cor para o que o serviço não descreve
    como preenchimento/contorno simples."""
    if not isinstance(drawing_info, dict):
        return None
    renderer = drawing_info.get("renderer")
    if not isinstance(renderer, dict) or renderer.get("type") != "simple":
        return None
    simbolo = renderer.get("symbol")
    if not isinstance(simbolo, dict):
        return None
    tipo = simbolo.get("type")
    if tipo in _TIPOS_SIMBOLO_POLIGONO:
        contorno = simbolo.get("outline") or {}
        return Simbologia(
            geometria="poligono",
            preenchimento_rgba=_cor(simbolo.get("color")),
            contorno_rgba=_cor(contorno.get("color")),
            contorno_largura=contorno.get("width"),
        )
    if tipo in _TIPOS_SIMBOLO_LINHA:
        return Simbologia(
            geometria="linha", preenchimento_rgba=None,
            contorno_rgba=_cor(simbolo.get("color")), contorno_largura=simbolo.get("width"),
        )
    return None  # esriPMS/esriSMS/picture: sem cor de preenchimento/contorno no sentido deste portão


@dataclass(frozen=True)
class Campo:
    nome: str
    tipo: str
    alias: str | None


@dataclass(frozen=True)
class DescricaoCamada:
    nome: str | None
    tipo_geometria: str | None  # esriGeometryPoint/Polyline/Polygon/... ou None (MapServer/ImageServer raiz)
    max_record_count: int
    campos: tuple[Campo, ...]
    simbologia: Simbologia | None
    copyright_texto: str | None
    descricao_servico: str | None
    capacidades: tuple[str, ...]  # `doc["capabilities"]` bruto, separado por vírgula (Query, Create, ...)


def descrever_servico(url_servico: str, token: str | None = None) -> dict:
    """`GET <url_servico>?f=json` cru (raiz do FeatureServer/MapServer/ImageServer) — usado pela rota
    `/esri/descricao` para listar `layers`/`tables`; devolvido bruto porque o formato da raiz varia bastante
    entre os três tipos de serviço (nada aqui é modelado em dataclass, ao contrário de `DescricaoCamada`)."""
    return _buscar_json(
        url_servico, token, timeout_s=limites.ESRI_REST_TIMEOUT_S, max_bytes=limites.ESRI_REST_DESCRICAO_MAX_BYTES,
    )


def descrever_camada(url_camada: str, token: str | None = None) -> DescricaoCamada:
    """`GET <url_camada>?f=json` — funciona tanto para uma layer de FeatureServer/MapServer
    (`.../FeatureServer/0`) quanto para a raiz de um MapServer/ImageServer sem sub-camada."""
    doc = _buscar_json(
        url_camada, token, timeout_s=limites.ESRI_REST_TIMEOUT_S, max_bytes=limites.ESRI_REST_DESCRICAO_MAX_BYTES,
    )
    campos = tuple(
        Campo(nome=c.get("name"), tipo=c.get("type"), alias=c.get("alias"))
        for c in doc.get("fields") or [] if isinstance(c, dict) and c.get("name")
    )
    capacidades_raw = doc.get("capabilities") or ""
    capacidades = tuple(p.strip() for p in capacidades_raw.split(",") if p.strip())
    return DescricaoCamada(
        nome=doc.get("name"),
        tipo_geometria=doc.get("geometryType"),
        max_record_count=int(doc.get("maxRecordCount") or limites.ESRI_REST_MAX_RECORD_COUNT_PADRAO),
        campos=campos,
        simbologia=simbologia_simples(doc.get("drawingInfo")),
        copyright_texto=doc.get("copyrightText") or None,
        descricao_servico=doc.get("serviceDescription") or doc.get("description") or None,
        capacidades=capacidades,
    )


# ------------------------------------------------------------------ contagem (returnCountOnly)


@dataclass(frozen=True)
class ResultadoContagem:
    ok: bool
    total: int | None
    mensagem: str


def contar(url_camada: str, where: str = "1=1", token: str | None = None) -> ResultadoContagem:
    """`.../query?where=...&returnCountOnly=true&f=json` — nunca baixa uma feição para contar; é o número
    que o próprio serviço declara ter para a cláusula do portão."""
    url = f"{url_camada.rstrip('/')}/query"
    alvo = _com_parametros(
        _url_com_token(url, token), {"where": where, "returnCountOnly": "true", "f": "json"},
    )
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.ESRI_REST_TIMEOUT_S,
        max_bytes=limites.ESRI_REST_DESCRICAO_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok:
        return ResultadoContagem(ok=False, total=None, mensagem=r.mensagem)
    try:
        doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ResultadoContagem(ok=False, total=None, mensagem="resposta_nao_e_json")
    if "error" in doc:
        erro = doc.get("error") or {}
        return ResultadoContagem(ok=False, total=None, mensagem=str(erro.get("message") or "erro_do_servico"))
    if "count" not in doc:
        return ResultadoContagem(ok=False, total=None, mensagem="resposta_sem_campo_count")
    return ResultadoContagem(ok=True, total=int(doc["count"]), mensagem="ok")


# ------------------------------------------------------------------ query paginado (feições)


@dataclass
class ResultadoConsulta:
    ok: bool
    formato: str
    feicoes: list = field(default_factory=list)   # cada item = 1 objeto GeoJSON Feature (formato="geojson")
    paginas_lidas: int = 0
    truncado: bool = False   # atingiu ESRI_REST_PAGINAS_MAX ou ESRI_REST_FEICOES_MAX antes de esgotar o servidor
    avisos: list[str] = field(default_factory=list)
    mensagem: str = "ok"


def consultar_pagina(
    url_camada: str, *, offset: int, tamanho: int, where: str = "1=1", out_fields: str = "*",
    out_sr: int = 4326, token: str | None = None,
) -> tuple[dict | None, str | None]:
    """Uma página só, formato geojson (o formato que a plataforma consome para desenhar/gravar). Devolve
    `(doc, None)` em sucesso ou `(None, mensagem_de_erro)`."""
    url = f"{url_camada.rstrip('/')}/query"
    alvo = _com_parametros(
        _url_com_token(url, token),
        {
            "where": where, "outFields": out_fields, "resultOffset": offset, "resultRecordCount": tamanho,
            "outSR": out_sr, "f": "geojson",
        },
    )
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.ESRI_REST_TIMEOUT_S,
        max_bytes=limites.ESRI_REST_PAGINA_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok:
        return None, r.mensagem
    try:
        doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "resposta_nao_e_json"
    if isinstance(doc, dict) and "error" in doc:
        erro = doc.get("error") or {}
        return None, str(erro.get("message") or "erro_do_servico")
    return doc, None


def consultar_tudo(
    url_camada: str, *, where: str = "1=1", out_fields: str = "*", out_sr: int = 4326,
    token: str | None = None, max_record_count_servico: int | None = None,
) -> ResultadoConsulta:
    """Pagina até o servidor parar de declarar `exceededTransferLimit`/devolver página cheia, respeitando
    SEMPRE `min(maxRecordCount do servidor, ESRI_REST_MAX_RECORD_COUNT_PADRAO)` por página — nunca pedimos
    mais do que o serviço aceita. Refutação do item (serviço com `maxRecordCount=1`): o laço para no teto
    `ESRI_REST_PAGINAS_MAX`, marca `truncado=True` e devolve o que já leu — nunca um laço infinito."""
    tamanho_pagina = max(1, min(
        max_record_count_servico or limites.ESRI_REST_MAX_RECORD_COUNT_PADRAO,
        limites.ESRI_REST_MAX_RECORD_COUNT_PADRAO,
    ))
    feicoes: list = []
    avisos: list[str] = []
    offset = 0
    pagina = 0
    hash_pagina_anterior: str | None = None
    while pagina < limites.ESRI_REST_PAGINAS_MAX and len(feicoes) < limites.ESRI_REST_FEICOES_MAX:
        pagina += 1
        doc, erro = consultar_pagina(
            url_camada, offset=offset, tamanho=tamanho_pagina, where=where, out_fields=out_fields,
            out_sr=out_sr, token=token,
        )
        if erro is not None:
            if pagina == 1:
                return ResultadoConsulta(ok=False, formato="geojson", mensagem=erro, paginas_lidas=0)
            avisos.append(f"parou na página {pagina}: {erro}")
            break
        novas = doc.get("features") or []
        if not novas:
            break
        # três travas independentes além do teto de páginas, mesma ideia do conector WFS (L6-02-c):
        # (1) página maior do que a pedida (servidor ignora resultRecordCount); (2) página IDÊNTICA à
        # anterior (servidor ignora resultOffset por completo — sem isto, o teto de páginas ainda pararia
        # o laço, mas só depois de acumular até ESRI_REST_PAGINAS_MAX cópias duplicadas da mesma página).
        hash_pagina_atual = hashlib.sha256(json.dumps(novas, sort_keys=True, default=str).encode()).hexdigest()
        if hash_pagina_anterior is not None and hash_pagina_atual == hash_pagina_anterior:
            avisos.append(
                f"parou na página {pagina}: idêntica à anterior (servidor ignora resultOffset) — "
                "sem isso o laço só pararia no teto de páginas, com dados duplicados"
            )
            break
        hash_pagina_anterior = hash_pagina_atual
        if len(novas) > tamanho_pagina:
            avisos.append(
                f"página {pagina} devolveu {len(novas)} feições, mais do que os {tamanho_pagina} pedidos "
                "(servidor ignora resultRecordCount) — aceita e segue, mas não confia no offset seguinte"
            )
        feicoes.extend(novas)
        exceded = doc.get("exceededTransferLimit") or (doc.get("properties") or {}).get("exceededTransferLimit")
        if not exceded and len(novas) < tamanho_pagina:
            offset += len(novas)
            break  # página incompleta e sem exceededTransferLimit: é a última
        offset += len(novas)
    else:
        if pagina >= limites.ESRI_REST_PAGINAS_MAX:
            avisos.append(
                f"parou em {limites.ESRI_REST_PAGINAS_MAX} páginas (teto de segurança) — o serviço pode ter "
                "mais feições; maxRecordCount efetivo usado foi {tamanho_pagina}".format(tamanho_pagina=tamanho_pagina)
            )
        if len(feicoes) >= limites.ESRI_REST_FEICOES_MAX:
            avisos.append(f"parou em {limites.ESRI_REST_FEICOES_MAX} feições (teto de segurança do modo referenciado)")
    truncado = bool(avisos)
    return ResultadoConsulta(
        ok=True, formato="geojson", feicoes=feicoes, paginas_lidas=pagina, truncado=truncado, avisos=avisos,
    )


# ------------------------------------------------------------------ export de imagem (MapServer/ImageServer)


@dataclass(frozen=True)
class ResultadoImagem:
    ok: bool
    content_type: str | None
    corpo: bytes
    mensagem: str


def _exportar(
    url_servico: str, caminho: str, *, bbox: tuple[float, float, float, float], largura: int, altura: int,
    out_sr: int, formato: str, token: str | None, extra: dict | None = None,
) -> ResultadoImagem:
    largura = max(1, min(largura, limites.ESRI_REST_IMAGEM_LADO_MAX))
    altura = max(1, min(altura, limites.ESRI_REST_IMAGEM_LADO_MAX))
    minx, miny, maxx, maxy = bbox
    url = f"{url_servico.rstrip('/')}/{caminho}"
    parametros = {
        "bbox": f"{minx},{miny},{maxx},{maxy}", "size": f"{largura},{altura}", "bboxSR": out_sr,
        "imageSR": out_sr, "format": formato, "transparent": "true", "f": "image",
    }
    parametros.update(extra or {})
    alvo = _com_parametros(_url_com_token(url, token), parametros)
    r = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.ESRI_REST_IMAGEM_TIMEOUT_S,
        max_bytes=limites.ESRI_REST_IMAGEM_MAX_BYTES, guardar_corpo=True,
    )
    if not r.ok:
        return ResultadoImagem(ok=False, content_type=None, corpo=b"", mensagem=r.mensagem)
    # o serviço pode devolver `{"error":...}` em JSON mesmo com f=image quando o pedido é inválido
    if r.corpo[:1] in (b"{", b"["):
        try:
            doc = json.loads(r.corpo.decode("utf-8", errors="replace"))
            if isinstance(doc, dict) and "error" in doc:
                erro = doc.get("error") or {}
                return ResultadoImagem(
                    ok=False, content_type=None, corpo=b"", mensagem=str(erro.get("message") or "erro_do_servico"),
                )
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    tipo = {"png": "image/png", "png32": "image/png", "jpg": "image/jpeg", "tiff": "image/tiff"}.get(
        formato.lower(), "application/octet-stream"
    )
    return ResultadoImagem(ok=True, content_type=tipo, corpo=r.corpo, mensagem="ok")


def exportar_mapa(
    url_servico: str, *, bbox: tuple[float, float, float, float], largura: int, altura: int,
    out_sr: int = 4326, formato: str = "png32", token: str | None = None, camadas: str | None = None,
) -> ResultadoImagem:
    """MapServer `/export`: imagem dinâmica renderizada pelo servidor (equivalente ao GetMap do WMS)."""
    extra = {"layers": f"show:{camadas}"} if camadas else None
    return _exportar(url_servico, "export", bbox=bbox, largura=largura, altura=altura, out_sr=out_sr,
                      formato=formato, token=token, extra=extra)


def exportar_imagem_raster(
    url_servico: str, *, bbox: tuple[float, float, float, float], largura: int, altura: int,
    out_sr: int = 4326, formato: str = "png", token: str | None = None,
) -> ResultadoImagem:
    """ImageServer `/exportImage`: raster referenciado (mesma forma do `_exportar`, endpoint diferente)."""
    return _exportar(url_servico, "exportImage", bbox=bbox, largura=largura, altura=altura, out_sr=out_sr,
                      formato=formato, token=token)
