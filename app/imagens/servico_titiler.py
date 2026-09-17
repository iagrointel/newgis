"""Serviço de ladrilho TiTiler por inquilino (item L1-02-a; unidade `plat-titiler`, 127.0.0.1:8152).

Este processo é SEPARADO do `plat-api`. Motivo: leitura de COG é trabalho de CPU e de espera de rede
(faixas de bytes no Garage) e, no mesmo processo da API, uma tela de mapa com 40 ladrilhos ocuparia os
trabalhadores que atendem formulário e login. Separar dá também limite de memória e reinício próprios
na unidade systemd, sem derrubar a API.

O motor é o TiTiler (`titiler.core` 2.2) — a decisão C5 do conceito L1 diz que não se escreve motor
raster próprio. O que NÃO se herda do TiTiler é o contrato de URL: as fábricas dele publicam
`/cog/tiles/...?url=<endereço>`, isto é, o cliente escolhe o arquivo a ler. Aqui esse parâmetro NÃO
existe:

  `path_dependency` recebe SÓ `token` e `item` do CAMINHO da URL, resolve o item em
  `plat.raster_item` do inquilino daquele token e devolve `/vsis3/<balde do inquilino>/<chave>`.

Duas consequências que são o produto deste item:
1. não há entrada do cliente que vire endereço de leitura, logo não há SSRF a explorar — e, para que
   isso não dependa de o TiTiler nunca ganhar um parâmetro novo, `recusar_endereco` varre TODOS os
   parâmetros de consulta e recusa com 400 qualquer valor que pareça endereço (`file:`, `s3:`,
   `http://169.254.169.254/`, `/vsicurl/`, ...), inclusive em `expression`, `colormap` e `assets`;
2. o item de outro inquilino responde 403, porque a consulta é filtrada por `tenant_id` do token e a
   linha simplesmente não aparece (nunca 404: a diferença entre "não existe" e "é de outro" é
   informação que não se dá).

Uma única grade (decisão C4): `WebMercatorQuad`. Com as 12 grades que o morecantile traz, o documento
de capacidades do WMTS cresce para 191 KB e leva 655 ms; com uma só, 18 KB e 143 ms (medido na entrega
deste item, ver `tests/medidas/L1-02-a-servico-titiler-por-inquilino.json`).

Credencial: a chave só-leitura do balde do inquilino é lida NA HORA do pedido (`objetos.fonte_gdal`) e
vive apenas dentro do `rasterio.Env` que envolve a leitura (`LeitorInquilino`). Nunca vira variável de
ambiente do processo, nunca volta ao cliente, nunca é a chave de escrita.
"""

from __future__ import annotations

import contextvars
import re
import time

import attr
import rasterio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from morecantile.defaults import TileMatrixSets
from morecantile.defaults import tms as registro_tms
from rio_tiler.io.rasterio import Reader
from starlette.concurrency import run_in_threadpool
from titiler.core.factory import TilerFactory

from app import erros
from app.erros import ErroAPI
from app.imagens.rotas_tiles import _asset_padrao, _autorizar, _fonte_do_item
from app.versao import versao

# Só WebMercatorQuad (decisão C4). `TileMatrixSets` aceita o dicionário nome -> definição; o registro do
# morecantile guarda o caminho do JSON e resolve na leitura, então basta reaproveitar a entrada dele.
GRADE = "WebMercatorQuad"
GRADES = TileMatrixSets({GRADE: registro_tms.tilematrixsets[GRADE]})

# O que este serviço recusa em QUALQUER parâmetro de consulta. Não é lista negra de hospedeiro (essa
# sempre tem um furo a mais): é a forma de um endereço. Um valor legítimo deste serviço — expressão
# aritmética, lista de bandas, faixa de números, nome de paleta, dicionário de cores — nunca contém
# esquema de URL nem prefixo de sistema de arquivos virtual do GDAL.
_ENDERECO = re.compile(
    r"(?:^|[\s,;\"'\[\{(])(?:[a-z][a-z0-9+.\-]{1,15}://|file:|s3:|gs:|az:|data:|//[0-9a-z])|/vsi[a-z0-9_]+/",
    re.IGNORECASE,
)
# nomes de parâmetro que o TiTiler original usa para receber endereço; barrados pelo nome, além do valor
PARAMETROS_DE_ENDERECO = {"url", "src_path", "input", "dataset", "path", "href", "endpoint"}
ITEM_VALIDO = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._\-]{0,127}$")

# fonte do pedido em curso (caminho + opções GDAL + sessão S3 só-leitura do balde do inquilino): posta
# pela dependência de caminho, lida pelo leitor. É variável de CONTEXTO, não global: cada requisição tem
# a sua, e a `run_in_threadpool` do Starlette copia o contexto para o trabalhador que abre o COG.
_FONTE_DO_PEDIDO: contextvars.ContextVar[object | None] = contextvars.ContextVar("plat_fonte_pedido", default=None)


@attr.s
class LeitorInquilino(Reader):
    """`rio_tiler.io.Reader` que abre o COG dentro da sessão S3 do inquilino do pedido.

    Por que não pelo `environment_dependency` do TiTiler: ele desemboca em `rasterio.Env(**opcoes)`, e o
    rasterio recusa `AWS_*` ali ("AWS config options can not be directly set"). A credencial tem de
    entrar como `session=AWSSession(...)`. O `_ctx_stack` do próprio Reader (uma `ExitStack`) é o lugar
    certo para prender o `Env`: entra antes do `rasterio.open` e sai no `close()` do leitor, então a
    credencial dura exatamente o tempo da leitura.
    """

    def __attrs_post_init__(self):
        fonte = _FONTE_DO_PEDIDO.get()
        if fonte is not None:
            self._ctx_stack.enter_context(rasterio.Env(session=fonte.sessao, **fonte.env))
        super().__attrs_post_init__()


def recusar_endereco(request: Request) -> None:
    """400 em qualquer tentativa de mandar endereço de arquivo por parâmetro de consulta.

    Vale para parâmetro que o TiTiler conhece (`expression`, `colormap`, `assets`, `algorithm`...) e
    para parâmetro que ele não conhece: a varredura é sobre o dicionário inteiro da consulta, não sobre
    uma lista de campos previstos. É a garantia de que uma versão futura do TiTiler que reintroduza
    `?url=` não abre buraco aqui."""
    for chave, valor in request.query_params.multi_items():
        nome = chave.strip().lower()
        if nome in PARAMETROS_DE_ENDERECO:
            raise ErroAPI(
                400, "endereco_nao_aceito",
                "este serviço não aceita endereço de arquivo: o COG é resolvido pelo item do catálogo",
                {"parametro": chave},
            )
        if _ENDERECO.search(valor or ""):
            raise ErroAPI(
                400, "endereco_nao_aceito",
                "valor com aparência de endereço em parâmetro de consulta",
                {"parametro": chave},
            )


async def caminho_do_item(request: Request, token: str, item: str) -> str:
    """`path_dependency` do TiTiler: SÓ token e item, os dois do caminho da URL.

    Devolve `/vsis3/<balde do inquilino>/<chave>` e deixa a credencial só-leitura na variável de
    contexto que o `LeitorInquilino` lê. Nenhum parâmetro de consulta participa da escolha do arquivo.
    """
    recusar_endereco(request)
    if not ITEM_VALIDO.match(item or ""):
        # o `..` do adversário morre aqui, antes de qualquer consulta; e `item` nunca vira caminho
        # relativo porque o caminho final é montado com o balde do inquilino, não com o texto do cliente
        raise ErroAPI(400, "item_invalido", "identificador de item fora do formato aceito", {"item": item})

    def _resolver():
        auth = _autorizar(request, token, item)
        expressao = request.query_params.get("expression")
        asset = request.query_params.get("asset")
        fonte, _stac = _fonte_do_item(auth, item, _asset_padrao(expressao, asset))
        return fonte

    fonte = await run_in_threadpool(_resolver)
    _FONTE_DO_PEDIDO.set(fonte)
    return fonte.caminho


def criar_app() -> FastAPI:
    app = FastAPI(
        title="plat — ladrilho raster por inquilino",
        version=versao(),
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    erros.instalar(app)

    @app.middleware("http")
    async def cabecalhos(request: Request, chamar):
        inicio = time.perf_counter()
        resposta = await chamar(request)
        ms = (time.perf_counter() - inicio) * 1000
        anterior = resposta.headers.get("Server-Timing")
        medida = f"total;dur={ms:.1f}"
        resposta.headers["Server-Timing"] = f"{anterior}, {medida}" if anterior else medida
        # o endereço do ladrilho é colado em mapa de terceiro e viraria página indexada sem isto
        resposta.headers["X-Robots-Tag"] = "noindex, nofollow"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        return resposta

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        """Sonda da unidade e do `/saude` do plat-api (PLAT_TITILER_URL). Não toca no banco de
        propósito: o que se pergunta aqui é se o processo do ladrilho está de pé."""
        return JSONResponse({"servico": "titiler", "grade": GRADE, "estado": "ok"},
                            headers={"Cache-Control": "no-store"})

    fabrica = TilerFactory(
        reader=LeitorInquilino,
        path_dependency=caminho_do_item,
        supported_tms=GRADES,
        router_prefix="/svc/{token}/raster/{item}",
        add_preview=False,
        add_part=False,
        add_viewer=False,
    )
    app.include_router(fabrica.router, prefix="/svc/{token}/raster/{item}", tags=["raster"])
    return app


app = criar_app()
