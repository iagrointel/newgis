"""Rotas de sessão da linha de imagens (item L1-01-ingest-raster; ADR 20260906T2127 decisões 6-7):

- `POST /api/imagens/ingestoes` — cria o job `imagens.ingestar` a partir de um item `arquivo` já enviado
  (upload retomável do L0-04-a; no navegador é o fluxo de web/js/uploads). É a porta "upload pelo
  navegador -> job" do portão.
- `GET /api/imagens/{item_id}` — painel do item raster: bbox, EPSG, estatísticas por banda, tamanhos,
  endereços dos tiles e da miniatura. É o que o Conteúdo e o mapa consomem (sessão/cookie ou token).
- `GET /api/imagens/{item_id}/tiles/{z}/{x}/{y}.png` — tile PNG 256 px WebMercator renderizado do COG
  visual, lido do Garage por Range através de um objeto arquivo-like (`ObjetoRemoto`) — nunca baixa o COG
  inteiro. Mínimo honesto até o TiTiler do L1-02 (mesma URL, implementação trocada).
- `POST /api/imagens/{item_id}/conferir` (item L1-01-j) — CONFERE a proveniência: rebaixa cada asset do
  balde em stream, recalcula o sha256 e compara com o registrado; a versão pesada (reconverte de verdade)
  é o job `imagens.reexecutar` (app/imagens/reexecucao.py), não uma rota — GDAL nunca roda dentro de uma
  requisição HTTP nesta casa.
- `POST /api/imagens/proveniencia/preencher-pendentes` (item L1-01-j) — preenchimento retroativo SEM
  reconversão para itens ingeridos antes deste item (rota de administração; o job `imagens.
  preencher_proveniencia` faz o mesmo item a item pela fila).

Isolamento: toda leitura passa por `db.db(auth.contexto())` (RLS de `plat.item`/`plat.raster_item`) e a
chave do COG vem do item STAC do PRÓPRIO inquilino — nunca de parâmetro de caminho livre.
"""

from __future__ import annotations

import io
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeout

import morecantile
import numpy as np
import rasterio
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import Field
from rasterio import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.imagens import pgstac as ps
from app.imagens import proveniencia as prov
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["imagens"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}
TILE_CACHE = {"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex, nofollow"}


_TMS = morecantile.tms.get("WebMercatorQuad")
_TILE_PX = 256


# ---------------------------------------------------------------- objeto remoto arquivo-like (Range no Garage)
class ObjetoRemoto(io.RawIOBase):
    """Arquivo binário seekable sobre um objeto do Garage: cada `read` vira um GET por intervalo
    (`objetos.ler_intervalo`), que é o mecanismo que torna o COG navegável sem download integral."""

    def __init__(self, chave: str):
        self._chave = chave
        self._tamanho = objetos.tamanho(chave)
        self._pos = 0
        self._fechado = False

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def seek(self, deslocamento: int, origem: int = io.SEEK_SET) -> int:
        if origem == io.SEEK_SET:
            novo = deslocamento
        elif origem == io.SEEK_CUR:
            novo = self._pos + deslocamento
        else:
            novo = self._tamanho + deslocamento
        self._pos = max(0, min(novo, self._tamanho))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, n: int = -1) -> bytes:
        if self._fechado:
            raise ValueError("leitura em objeto fechado")
        if self._pos >= self._tamanho:
            return b""
        if n is None or n < 0:
            n = self._tamanho - self._pos
        fim = min(self._tamanho, self._pos + n) - 1
        dados = objetos.ler_intervalo(self._chave, self._pos, fim)
        self._pos += len(dados)
        return dados

    def readinto(self, b) -> int:
        dados = self.read(len(b))
        b[: len(dados)] = dados
        return len(dados)

    def close(self) -> None:
        self._fechado = True
        super().close()


# ---------------------------------------------------------------- cache de datasets abertos (LRU por processo)
class _CacheDatasets:
    """LRU de datasets rasterio abertos sobre ObjetoRemoto, teto RASTER_TILE_CACHE_DATASET_MAX (o limite é
    declarado em app.limites: cada dataset aberto segura estruturas do GDAL). Uma trava única serializa o
    acesso — datasets rasterio não são thread-safe."""

    def __init__(self, tamanho: int):
        self._tamanho = max(1, tamanho)
        self._mapa: OrderedDict[str, rasterio.io.DatasetReader] = OrderedDict()
        self._trava = threading.Lock()

    def ler_janela(self, chave: str, esquerda: float, baixo: float, direita: float, cima: float) -> np.ma.MaskedArray:
        with self._trava:
            ds = self._mapa.get(chave)
            if ds is None or ds.closed:
                ds = rasterio.open(ObjetoRemoto(chave))
                self._mapa[chave] = ds
                self._mapa.move_to_end(chave)
                while len(self._mapa) > self._tamanho:
                    _, velho = self._mapa.popitem(last=False)
                    try:
                        velho.close()
                    except Exception:  # noqa: BLE001 — fechar dataset expulso nunca derruba um tile
                        pass
            # BUG MEDIDO 10/09: nesta versão do rasterio (1.5.0), `WarpedVRT.read(boundless=True)` recusa
            # INCONDICIONALMENTE ("WarpedVRT does not permit boundless reads") — nunca exercido até o mapa
            # ligar uma camada raster de verdade (só o `/svc/.../raster/...` baseado em rio-tiler tinha
            # cobertura de teste). O jeito certo, que qualquer tiler de COG usa: o VRT de destino já É o
            # ladrilho — `transform`/`width`/`height` do PRÓPRIO tile — a leitura nunca sai dos limites do
            # VRT e o GDAL mascara sozinho o que cai fora da cobertura da imagem de origem.
            transform_do_tile = Affine((direita - esquerda) / _TILE_PX, 0.0, esquerda,
                                        0.0, (baixo - cima) / _TILE_PX, cima)
            with WarpedVRT(ds, crs="EPSG:3857", resampling=Resampling.bilinear,
                            transform=transform_do_tile, width=_TILE_PX, height=_TILE_PX) as vrt:
                return vrt.read(masked=True)


_CACHE = _CacheDatasets(limites.RASTER_TILE_CACHE_DATASET_MAX)
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tile")


def _png_de(arr: np.ma.MaskedArray) -> bytes:
    """PNG RGBA: alfa = máscara do raster (fora da imagem/nodata transparente); com 4 bandas o alfa do
    WEBP manda; 1 banda vira cinza."""
    bandas = arr.shape[0]
    if bandas >= 4:
        rgba = np.dstack([arr[0].filled(0), arr[1].filled(0), arr[2].filled(0), arr[3].filled(0)])
    elif bandas == 3:
        alfa = np.where(arr[0].mask | arr[1].mask | arr[2].mask, 0, 255).astype("uint8")
        rgba = np.dstack([arr[0].filled(0), arr[1].filled(0), arr[2].filled(0), alfa])
    elif bandas == 2:
        rgba = np.dstack([arr[0].filled(0)] * 3 + [arr[1].filled(0)])
    else:
        alfa = np.where(arr[0].mask, 0, 255).astype("uint8")
        rgba = np.dstack([arr[0].filled(0)] * 3 + [alfa])
    img = Image.fromarray(rgba.astype("uint8"), mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- carga do item (RLS) e chave do COG visual
def _item_raster(cur, item_id: str) -> dict:
    iid = uuid_ok(item_id, "item_inexistente", "item inexistente")
    cur.execute(
        "SELECT id, titulo, dados, tamanho_bytes, miniatura_chave, criado_em FROM plat.item "
        "WHERE id = %s::uuid AND tipo = 'raster'",
        (iid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


def _chave_visual(cur, tenant_id: int, dados: dict) -> str:
    """Chave do COG visual lida do item STAC do próprio inquilino (fonte única: pgstac)."""
    colecao = (dados or {}).get("colecao") or ""
    stac_id = (dados or {}).get("stac_id") or ""
    if not ps.colecao_pertence(colecao, tenant_id):
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    stac = ps.item_obter(cur, tenant_id, colecao, stac_id)
    if stac is None:
        raise ErroAPI(404, "item_inexistente", "item STAC inexistente")
    href = ((stac.get("assets") or {}).get("visual") or {}).get("href") or ""
    if not href.startswith("/api/objetos/"):
        raise ErroAPI(404, "objeto_inexistente", "o item STAC não tem asset visual endereçável")
    return href[len("/api/objetos/"):]


# ---------------------------------------------------------------- ingestão (upload -> job)
class IngestaoEntrada(Modelo):
    arquivo_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    titulo: str | None = Field(default=None, min_length=1, max_length=250)
    epsg_declarado: int | None = Field(default=None, ge=1, le=999999)


@router.post("/api/imagens/ingestoes", status_code=202, openapi_extra=PUBLICAR)
def ingestao_criar(corpo: IngestaoEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    arquivo_id = uuid_ok(corpo.arquivo_id, "item_inexistente", "item de arquivo inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (arquivo_id,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "item_inexistente", "item de arquivo inexistente")
    job = servico.criar(sessao_de(auth), "imagens.ingestar", {
        "arquivo_id": arquivo_id, "titulo": corpo.titulo, "epsg_declarado": corpo.epsg_declarado,
    })
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "imagens/ingestar", "item", arquivo_id, {"job_id": job["id"]})
    return {"job_id": job["id"], "estado": job["estado"]}


# ---------------------------------------------------------------- painel do item (Conteúdo / mapa)
@router.get("/api/imagens/{item_id}", openapi_extra=LER)
def imagem_ver(item_id: str, auth: Auth = autenticado(escopo_token="imagens:ler")):
    with db.db(auth.contexto()) as cur:
        item = _item_raster(cur, item_id)
        dados = item["dados"] or {}
        colecao = dados.get("colecao") or ""
        stac = None
        if ps.colecao_pertence(colecao, auth.tenant_id):
            stac = ps.item_obter(cur, auth.tenant_id, colecao, dados.get("stac_id") or "")
    corpo = {
        "item_id": str(item["id"]),
        "titulo": item["titulo"],
        "colecao": colecao,
        "stac_id": dados.get("stac_id"),
        "srid_nativo": dados.get("srid_nativo"),
        "perfil": dados.get("perfil"),
        "origem": dados.get("origem"),
        "bandas": dados.get("bandas") or [],
        "tamanho_bytes": item["tamanho_bytes"],
        "tem_miniatura": bool(item["miniatura_chave"]),
        "miniatura_url": f"/api/itens/{item['id']}/miniatura",
        "tiles_url": f"/api/imagens/{item['id']}/tiles/{{z}}/{{x}}/{{y}}.png",
        # item L2-01-mapa-web (10/09): a imagem entra na lista de camadas do mapa junto com os vetores;
        # o front usa isto para ordenar "as N mais recentes" quando decide o padrão de visibilidade.
        "criado_em": item["criado_em"].isoformat() if item["criado_em"] else None,
    }
    if stac is not None:
        props = stac.get("properties") or {}
        corpo["bbox"] = stac.get("bbox")
        corpo["geometria"] = stac.get("geometry")
        corpo["estatisticas"] = (
            ((stac.get("assets") or {}).get("cientifico") or {}).get("raster:bands") or []
        )
        corpo["epsg"] = props.get("proj:epsg")
        corpo["dimensoes"] = props.get("proj:shape")
        corpo["avisos_validacao"] = props.get("plat:avisos") or props.get("plat:avisos_validacao") or []
        corpo["assets"] = {nome: {"type": a.get("type"), "file:size": a.get("file:size"),
                                  "file:checksum": a.get("file:checksum")}
                           for nome, a in (stac.get("assets") or {}).items()}
        # item L1-01-j: proveniência verificável — a "ficha" do item mostra a cadeia em texto simples
        # (comando + sha256 de entrada/saída de cada passo), nunca só uma promessa em prosa.
        corpo["proveniencia"] = {
            "processing_software": props.get("processing:software"),
            "processing_lineage": props.get("processing:lineage"),
            "cadeia": props.get("plat:cadeia"),
            "cadeia_origem": props.get("plat:cadeia_origem"),
            "manifesto_sha256": props.get("plat:manifesto_sha256"),
            "reexecucao": props.get("plat:reexecucao"),
        }
    return JSONResponse(corpo, headers=SEM_CACHE)


# ---------------------------------------------------------------- tiles
@router.get("/api/imagens/{item_id}/tiles/{z}/{x}/{y}.png", openapi_extra=LER)
def tile(item_id: str, z: int, x: int, y: int, auth: Auth = autenticado(escopo_token="imagens:ler")):
    if z < 0 or z > 24 or x < 0 or y < 0 or x >= 2 ** z or y >= 2 ** z:
        raise ErroAPI(422, "tile_invalido", f"coordenada de tile inválida: z={z} x={x} y={y}")
    with db.db(auth.contexto()) as cur:
        item = _item_raster(cur, item_id)
        chave = _chave_visual(cur, auth.tenant_id, item["dados"] or {})
    try:
        # BUG MEDIDO 10/09: `_TMS.tile(x, y, z)` calcula um tile A PARTIR DE lng/lat — chamá-lo com
        # índices de tile (x=1518 não é longitude válida) sempre disparava `PointOutsideTMSBounds` e
        # devolvia um `Tile` sem `.left/.bottom/...` (`AttributeError`), nunca exercido até o mapa
        # ligar a camada raster de verdade. O índice já É o tile — o que falta é a CAIXA dele em metros
        # (`ler_janela` abre o VRT em EPSG:3857, não em graus), que é `xy_bounds`, não `.tile()`; mesmo
        # padrão já usado em app/imagens/rotas_tiles.py.
        caixa = _TMS.xy_bounds(morecantile.Tile(x, y, z))
    except morecantile.errors.InvalidZoomError as e:
        raise ErroAPI(422, "tile_invalido", str(e)) from e
    try:
        futuro = _POOL.submit(_CACHE.ler_janela, chave, caixa.left, caixa.bottom, caixa.right, caixa.top)
        arr = futuro.result(timeout=limites.RASTER_TILE_TIMEOUT_S)
    except FuturoTimeout:
        raise ErroAPI(504, "tile_tempo_esgotado",
                      f"a renderização do tile passou de {limites.RASTER_TILE_TIMEOUT_S} s") from None
    except (rasterio.errors.RasterioError, FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(502, "tile_falhou", f"não foi possível ler o COG do item: {str(e)[:200]}") from e
    return Response(_png_de(arr), media_type="image/png", headers=TILE_CACHE)


# ---------------------------------------------------------------- proveniência (item L1-01-j)
class PreencherPendentesEntrada(Modelo):
    limite: int = Field(default=200, ge=1, le=2000)


@router.post("/api/imagens/{item_id}/conferir", openapi_extra=LER)
def imagem_conferir(item_id: str, request: Request, auth: Auth = autenticado(escopo_token="imagens:ler")):
    """Confere a proveniência do item: rebaixa cada asset com `file:checksum` do balde EM STREAM (nunca o
    objeto inteiro em RAM — o COG científico de uma cena chega a centenas de MB), recalcula o sha256 e
    compara com o registrado; recalcula também `plat:manifesto_sha256`. Devolve divergência por ativo — é o
    mecanismo que torna a proveniência do Lastro CONFERÍVEL, não prometida (a mesma ideia por trás de
    `imagens.reexecutar`, que além de conferir também reconverte)."""
    with db.db(auth.contexto()) as cur:
        item = _item_raster(cur, item_id)
        dados = item["dados"] or {}
        colecao = dados.get("colecao") or ""
        stac_id = dados.get("stac_id") or item_id
        if not ps.colecao_pertence(colecao, auth.tenant_id):
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        resultado = prov.conferir_item(cur, auth.tenant_id, colecao, stac_id)
        registrar_evento(cur, request, "imagens/conferir", "item", item_id,
                         {"ok": resultado["ok"], "n_ativos": len(resultado["ativos"])})
    return JSONResponse(resultado, headers=SEM_CACHE)


@router.post("/api/imagens/proveniencia/preencher-pendentes", openapi_extra=PUBLICAR)
def proveniencia_preencher_pendentes(
    corpo: PreencherPendentesEntrada, request: Request,
    auth: Auth = autenticado("conteudo.publicar_camada"),
):
    """Rota de administração do preenchimento retroativo (item L1-01-j, cláusula 3): busca até `limite`
    itens do inquilino cujo `plat:cadeia_origem` ainda NÃO existe (`prov.itens_pendentes`, filtro no jsonb
    do pgstac — nunca itera item já preenchido) e preenche, SEM reconverter — mesma lógica de
    `imagens.preencher_proveniencia`, mas inline (é leitura+escrita de metadado, nunca GDAL, então cabe
    numa requisição só). Item que precisa da cadeia MEDIDA de verdade (não reconstruída) segue precisando
    de `imagens.reexecutar` (fila, pesado). MEDIDO (10/09): sem o filtro de pendência, uma varredura
    repetida numa base com muito item já preenchido custava 165 s para ~217 itens só para descartar todos;
    com o filtro, uma base já preenchida volta em milissegundos com 0 pendente."""
    with db.db(auth.contexto()) as cur:
        pendentes = prov.itens_pendentes(cur, auth.tenant_id, corpo.limite)
        preenchidos, ja_tinha, falhas = 0, 0, []
        for colecao, item_id in pendentes:
            try:
                stac = ps.item_obter(cur, auth.tenant_id, colecao, item_id)
                if stac is None:
                    falhas.append({"item_id": item_id, "erro": "item STAC inexistente"})
                    continue
                novo = prov.preencher_leve(cur, auth.tenant_id, colecao, item_id, stac)
                if novo is None:
                    ja_tinha += 1
                else:
                    preenchidos += 1
            except Exception as e:  # noqa: BLE001 — 1 item ruim não pode derrubar a varredura dos outros
                falhas.append({"item_id": item_id, "erro": str(e)[:300]})
        registrar_evento(cur, request, "imagens/preencher_proveniencia_lote", "colecao", None,
                         {"preenchidos": preenchidos, "ja_tinha": ja_tinha, "falhas": len(falhas)})
    return JSONResponse(
        {"varridos": len(pendentes), "preenchidos": preenchidos, "ja_tinha": ja_tinha, "falhas": falhas},
        headers=SEM_CACHE,
    )
