"""Motor de ladrilho raster (item L1-02-tiles-token; ADR 20260907T0300).

Lê o COG do inquilino no Garage por `/vsis3` (leitura por faixa de bytes, sem baixar o arquivo) e
devolve o ladrilho já codificado. O motor é o rio-tiler 9.4.3 — a mesma biblioteca que roda dentro do
TiTiler (decisão C5 do conceito L1: não se escreve motor raster próprio). O que NÃO se herda do TiTiler
é o contrato de URL: a decisão C6 fixa `/svc/<token>/raster/<item>/{z}/{x}/{y}`, com o token no CAMINHO,
e as fábricas de rota do TiTiler publicam outra forma (`/tiles/{tileMatrixSetId}/{z}/{x}/{y}` com
`?url=`). Aqui não existe parâmetro `url`: o caminho do arquivo NASCE da consulta ao catálogo do
inquilino autenticado, e é por isso que não há SSRF a testar — não há entrada do cliente que vire
endereço de leitura.

Grade: só WebMercatorQuad (decisão C4). Expressão: sintaxe do rio-tiler (numexpr) restrita por
gramática própria antes de chegar ao avaliador (`expressao_valida`)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import rasterio
from morecantile import tms as tms_registry
from rasterio.crs import CRS
from rasterio.session import AWSSession
from rio_tiler.colormap import cmap as colormaps
from rio_tiler.errors import EmptyMosaicError, TileOutsideBounds
from rio_tiler.io import Reader

TMS = tms_registry.get("WebMercatorQuad")
TAMANHO = 256
FORMATOS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
RENDER = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}
COLORMAPS = set(colormaps.list())

# gramática da expressão: referência de banda (b1..b99), número, operador aritmético, parênteses, vírgula
# e um punhado de funções do numexpr. Tudo o que não casa é recusado ANTES de o texto chegar ao avaliador.
FUNCOES = ("where", "sqrt", "log", "log10", "exp", "abs", "minimum", "maximum", "sin", "cos", "arctan")
_TOKEN = re.compile(
    r"\s*(?:(?P<banda>b[0-9]{1,2})|(?P<numero>[0-9]+(?:\.[0-9]+)?)|(?P<funcao>[a-z][a-z0-9_]*)"
    r"|(?P<op>[-+*/(),<>]|>=|<=|==|!=))"
)
EXPRESSAO_MAX = 200


class ErroTile(RuntimeError):
    """Falha de leitura/renderização com mensagem já em português."""


class ForaDaCobertura(ErroTile):
    """O ladrilho pedido não intersecta o raster (resposta: 204, não 404 — o mapa segue navegável)."""


def expressao_valida(texto: str) -> tuple[bool, str]:
    """(ok, motivo). Recusa por gramática, não por lista negra: só passa o que a gramática reconhece."""
    if not texto or len(texto) > EXPRESSAO_MAX:
        return False, f"expressão vazia ou acima de {EXPRESSAO_MAX} caracteres"
    if "__" in texto:
        return False, "expressão com '__'"
    pos, tem_banda = 0, False
    while pos < len(texto):
        m = _TOKEN.match(texto, pos)
        if not m:
            return False, f"trecho não reconhecido na posição {pos}: {texto[pos:pos + 12]!r}"
        if m.group("funcao") and m.group("funcao") not in FUNCOES:
            return False, f"função não permitida: {m.group('funcao')} (permitidas: {', '.join(FUNCOES)})"
        tem_banda = tem_banda or bool(m.group("banda"))
        pos = m.end()
        while pos < len(texto) and texto[pos].isspace():
            pos += 1
    if not tem_banda:
        return False, "expressão sem nenhuma referência de banda (b1, b2, ...)"
    return True, ""


def bandas_da_expressao(texto: str) -> list[int]:
    return sorted({int(n) for n in re.findall(r"\bb([0-9]{1,2})\b", texto)})


@dataclass(frozen=True)
class Fonte:
    """De onde o ladrilho é lido: caminho GDAL, opções de ambiente e a sessão S3 (credencial só-leitura
    do balde do inquilino). A credencial nunca sai daqui: vive no `rasterio.Env` que envolve a leitura."""
    caminho: str
    env: dict
    sessao: object | None = None


# GDAL só fala com o Garage em HTTP e com endereço no caminho (path-style). As duas opções valem para a
# instalação inteira (é o MESMO endpoint para todo inquilino), não para uma leitura — por isso ficam no
# ambiente do processo e não no `Env` por requisição. O que é por inquilino é a credencial, e essa vai na
# sessão. O rasterio recusa `AWS_*` dentro de `Env` (erro "AWS config options can not be directly set").
def preparar_ambiente_s3(endpoint: str) -> None:
    os.environ.setdefault("AWS_HTTPS", "YES" if endpoint.startswith("https://") else "NO")
    os.environ.setdefault("AWS_VIRTUAL_HOSTING", "FALSE")


def sessao_s3(opcoes: dict) -> AWSSession:
    """Sessão de leitura a partir do que `app.objetos.fonte_gdal` devolveu."""
    return AWSSession(
        aws_access_key_id=opcoes["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=opcoes["AWS_SECRET_ACCESS_KEY"],
        region_name=opcoes.get("AWS_DEFAULT_REGION"),
        endpoint_url=opcoes.get("AWS_S3_ENDPOINT"),
    )


def env_gdal(extra: dict | None = None) -> dict:
    """Opções fixas de leitura de COG remoto (nenhuma delas é credencial)."""
    base = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_INGESTED_BYTES_AT_OPEN": 32768,
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": 64 * 1024 * 1024,
        "GDAL_NUM_THREADS": 1,
        "GDAL_CACHEMAX": 128,
    }
    base.update(extra or {})
    return base


def _colormap(nome: str | None):
    if not nome:
        return None
    if nome not in COLORMAPS:
        raise ErroTile(f"colormap desconhecido: {nome}")
    return colormaps.get(nome)


def colormap_de(nome: str | None):
    """Wrapper público de `_colormap` — usado fora deste módulo (ImageServer/`renderingRule`, item
    L1-02-f) sem alcançar o nome privado."""
    return _colormap(nome)


def ladrilho(
    fonte: Fonte,
    z: int,
    x: int,
    y: int,
    *,
    formato: str = "png",
    expressao: str | None = None,
    bandas: list[int] | None = None,
    rescale: list[tuple[float, float]] | None = None,
    colormap: str | None = None,
    tamanho: int = TAMANHO,
    resampling: str = "nearest",
    nodata_transparente: bool = True,
) -> bytes:
    """Bytes do ladrilho já codificado. Levanta ForaDaCobertura quando o ladrilho não toca o raster.

    `resampling`/`nodata_transparente` nasceram com o item L1-02-f (predefinição de renderização):
    antes disso o reamostro era sempre `nearest` e a máscara de nodata sempre virava alfa em PNG/WEBP
    — os dois seguem PADRÃO (comportamento idêntico ao de antes para quem não passa predefinição
    nenhuma; portão do item: "não mude o comportamento atual sem parâmetro")."""
    if formato not in RENDER:
        raise ErroTile(f"formato de ladrilho desconhecido: {formato}")
    if expressao is not None:
        ok, motivo = expressao_valida(expressao)
        if not ok:
            raise ErroTile(f"expressão recusada: {motivo}")
    cm = _colormap(colormap)
    indices = bandas if (bandas and not expressao) else None
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=TMS) as src:
            try:
                if indices is None and not expressao and src.dataset.count > 3:
                    # PNG/JPEG/WEBP não carregam mais de 3 bandas + máscara: sem escolha do cliente,
                    # vale a regra escrita do perfil visual (C3 do conceito L1) — as 3 primeiras bandas.
                    indices = (1, 2, 3)
                img = src.tile(x, y, z, tilesize=tamanho, expression=expressao, indexes=indices,
                               resampling_method=resampling)
            except TileOutsideBounds as e:
                raise ForaDaCobertura(str(e)) from e
            if rescale:
                img.rescale(rescale)
            elif expressao or (img.array.dtype != "uint8"):
                # sem faixa declarada, o dado que não é 8 bits precisa de uma: usa o mínimo/máximo do
                # próprio ladrilho (declarado na resposta pelo cabeçalho, nunca escondido)
                dados = img.array
                lo = float(dados.min()) if dados.size else 0.0
                hi = float(dados.max()) if dados.size else 1.0
                img.rescale([(lo, hi if hi > lo else lo + 1e-9)])
            add_mask = (RENDER[formato] != "JPEG") and nodata_transparente
            return img.render(img_format=RENDER[formato], colormap=cm, add_mask=add_mask)


def _imagem_vazia(width: int, height: int, formato: str, transparente: bool) -> bytes:
    """PNG/JPEG do tamanho pedido sem nenhum pixel de dado (fora da cobertura do raster). Diferente do
    ladrilho XYZ — que devolve 204 porque o mapa segue navegável sem aquela célula —, o GetMap do WMS
    promete uma imagem do TAMANHO exato pedido (§7.3.3.3 da spec): um cliente que pede 800x600 e recebe
    204 quebra a composição da tela. `transparente=False` pinta branco (o mesmo branco que GeoServer usa
    de fundo quando TRANSPARENT=FALSE, na ausência de BGCOLOR)."""
    from PIL import Image

    modo, cor = ("RGBA", (0, 0, 0, 0)) if transparente else ("RGB", (255, 255, 255))
    img = Image.new(modo, (width, height), cor)
    import io
    buf = io.BytesIO()
    img.save(buf, format=RENDER[formato])
    return buf.getvalue()


def recorte(
    fonte: Fonte,
    bbox: tuple[float, float, float, float],
    crs: str,
    width: int,
    height: int,
    *,
    formato: str = "png",
    expressao: str | None = None,
    bandas: list[int] | None = None,
    rescale: list[tuple[float, float]] | None = None,
    colormap: str | None = None,
    transparente: bool = True,
    resampling: str = "nearest",
) -> bytes:
    """Bytes de um recorte arbitrário já codificado — a função IRMÃ de `ladrilho()` acima, e o motivo de
    existirem duas: `ladrilho()` lê uma célula FIXA da grade WebMercantor (z/x/y, sempre 256x256, sempre
    3857) porque é isso que o XYZ/WMTS/TMS pedem; o WMS `GetMap` pede um retângulo ARBITRÁRIO — bbox,
    CRS e WIDTH/HEIGHT escolhidos pelo cliente a cada requisição — que não existe em nenhuma grade
    pré-calculada. `Reader.part()` (rio-tiler) já resolve exatamente isso: lê e reprojeta o COG direto
    para o bbox+CRS pedidos, sem passar pela grade de tile. `bbox` chega aqui SEMPRE na ordem
    (oeste, sul, leste, norte) do próprio `crs` — a troca de eixo do WMS 1.3.0 em EPSG:4326 (lat,lon no
    parâmetro BBOX) é resolvida por quem chama (`app/imagens/wms.py`), nunca aqui: este módulo só fala
    a ordem "normal" (x cresce para leste, y cresce para norte), igual ao resto do arquivo."""
    if formato not in RENDER:
        raise ErroTile(f"formato de imagem desconhecido: {formato}")
    if expressao is not None:
        ok, motivo = expressao_valida(expressao)
        if not ok:
            raise ErroTile(f"expressão recusada: {motivo}")
    cm = _colormap(colormap)
    indices = bandas if (bandas and not expressao) else None
    crs_obj = CRS.from_user_input(crs)  # aceita string ("EPSG:4326") explicitamente, sem depender de
    # coerção implícita do rio-tiler/rasterio — a tipagem de `Reader.part` pede `rasterio.crs.CRS`.
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=TMS) as src:
            if indices is None and not expressao and src.dataset.count > 3:
                indices = (1, 2, 3)
            try:
                img = src.part(
                    bbox, dst_crs=crs_obj, bounds_crs=crs_obj, indexes=indices, expression=expressao,
                    width=width, height=height, resampling_method=resampling,
                )
            except TileOutsideBounds:
                return _imagem_vazia(width, height, formato, transparente)
            # `img.mask` é o array de máscara no estilo rasterio (0 = sem dado); quando o máximo é 0,
            # NENHUM pixel do recorte toca o raster — mesmo caso do `ladrilho()`, só que `part()` não
            # levanta `TileOutsideBounds` para isso (ela só existe no caminho de `.tile()`).
            if int(img.mask.max()) == 0:
                return _imagem_vazia(width, height, formato, transparente)
            if rescale:
                img.rescale(rescale)
            elif expressao or (img.array.dtype != "uint8"):
                dados = img.array
                lo = float(dados.min()) if dados.size and not dados.mask.all() else 0.0
                hi = float(dados.max()) if dados.size and not dados.mask.all() else 1.0
                img.rescale([(lo, hi if hi > lo else lo + 1e-9)])
            return img.render(
                img_format=RENDER[formato], colormap=cm,
                add_mask=(RENDER[formato] != "JPEG") and transparente,
            )


METODOS_COMPOSICAO = {
    # item L1-08 (mínimo): 4 dos 7 métodos citados na hipótese — os que o rio-tiler já embute prontos,
    # sem exigir máscara de nuvem (SCL) nem "travar cena", que ficam de fora deste turno. Nomes em
    # português na API (`metodo=`); o valor é resolvido para a classe do rio_tiler aqui, uma vez só.
    "primeira": "FirstMethod", "mediana": "MedianMethod", "media": "MeanMethod",
    "maxima": "HighestMethod", "minima": "LowestMethod",
}


def _metodo_composicao(nome: str | None):
    from rio_tiler.mosaic.methods import defaults

    chave = nome or "primeira"
    classe = METODOS_COMPOSICAO.get(chave)
    if classe is None:
        raise ErroTile(f"método de composição desconhecido: {chave} (aceitos: {', '.join(sorted(METODOS_COMPOSICAO))})")
    return getattr(defaults, classe)


def ladrilho_composto(
    fontes: list[Fonte],
    z: int,
    x: int,
    y: int,
    *,
    formato: str = "png",
    expressao: str | None = None,
    bandas: list[int] | None = None,
    rescale: list[tuple[float, float]] | None = None,
    colormap: str | None = None,
    tamanho: int = TAMANHO,
    metodo: str | None = None,
) -> bytes:
    """Ladrilho de VÁRIAS fontes candidatas compostas num só (item L1-07: mosaico de busca
    registrada). Reaproveita `rio_tiler.mosaic.mosaic_reader` — a MESMA função que o `titiler.mosaic`/
    `titiler-pgstac` usam por baixo (ver ADR 20260910T2330 §1) — com o método de seleção de pixel
    escolhido por `metodo` (padrão `primeira`: "primeira fonte com dado vence", item L1-07) aplicado
    PIXEL A PIXEL (não cena a cena): onde a primeira fonte da lista não cobre o ladrilho (ou cobre só
    em parte), o(s) pixel(s) que faltam vêm da segunda, da terceira, e assim por diante — é o que faz
    o ladrilho da JUNTA entre duas cenas mostrar as duas, em vez de escolher uma cena inteira e deixar
    o resto transparente (o defeito do mosaico "cena inteira" que este item substitui). `mediana`/
    `media`/`maxima`/`minima` são o MÍNIMO do item irmão L1-08 (regras de seleção): "travar cena" e
    "mais recente sem nuvem" (dependem de máscara SCL) ficam fora deste turno. Levanta
    `ForaDaCobertura` quando NENHUMA fonte cobre o ladrilho; `ErroTile` se `metodo` for desconhecido."""
    if formato not in RENDER:
        raise ErroTile(f"formato de ladrilho desconhecido: {formato}")
    if expressao is not None:
        ok, motivo = expressao_valida(expressao)
        if not ok:
            raise ErroTile(f"expressão recusada: {motivo}")
    metodo_classe = _metodo_composicao(metodo)
    from rio_tiler.mosaic import mosaic_reader

    cm = _colormap(colormap)
    indices_pedidos = bandas if (bandas and not expressao) else None

    def _ler(fonte: Fonte, xx: int, yy: int, zz: int):
        indices = indices_pedidos
        with rasterio.Env(session=fonte.sessao, **fonte.env):
            with Reader(fonte.caminho, tms=TMS) as src:
                if indices is None and not expressao and src.dataset.count > 3:
                    indices = (1, 2, 3)
                return src.tile(xx, yy, zz, tilesize=tamanho, expression=expressao, indexes=indices)

    # Uma fonte por vez limita buffers GDAL e resultados pendentes a um tile de 256×256.
    # chunk_size=1 também permite parar assim que FirstMethod preencher o ladrilho.
    try:
        img, usadas = mosaic_reader(
            fontes, _ler, x, y, z, pixel_selection=metodo_classe, threads=1, chunk_size=1,
            allowed_exceptions=(TileOutsideBounds,),
        )
    except EmptyMosaicError as e:
        raise ForaDaCobertura("nenhuma cena candidata contém pixels neste ladrilho") from e
    if not usadas or not img.mask.any():
        raise ForaDaCobertura(f"nenhuma das {len(fontes)} cena(s) candidata(s) cobre o ladrilho {z}/{x}/{y}")
    if rescale:
        img.rescale(rescale)
    elif expressao or (img.array.dtype != "uint8"):
        dados = img.array
        lo = float(dados.min()) if dados.size and not dados.mask.all() else 0.0
        hi = float(dados.max()) if dados.size and not dados.mask.all() else 1.0
        img.rescale([(lo, hi if hi > lo else lo + 1e-9)])
    return img.render(img_format=RENDER[formato], colormap=cm, add_mask=RENDER[formato] != "JPEG")


def informacao(fonte: Fonte) -> dict:
    """bounds em 4326, número de bandas, dtype e zoom mínimo/máximo — base do TileJSON e do WMTS."""
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=TMS) as src:
            info = src.info()
            return {
                "bounds": [round(v, 7) for v in src.get_geographic_bounds("EPSG:4326")],
                "minzoom": src.minzoom,
                "maxzoom": src.maxzoom,
                "bandas": len(info.band_descriptions),
                "dtype": info.dtype,
                "nodata": info.nodata_value,
            }


__all__ = [
    "COLORMAPS", "ErroTile", "ForaDaCobertura", "Fonte", "FORMATOS", "METODOS_COMPOSICAO", "TMS", "TAMANHO",
    "bandas_da_expressao", "env_gdal", "expressao_valida", "informacao", "ladrilho", "ladrilho_composto",
    "recorte", "preparar_ambiente_s3", "sessao_s3",
]
