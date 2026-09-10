"""Proxy autenticado do notebook por inquilino (L2-16-b): /notebooks/<slug>/... com SESSÃO da
plataforma (cookie; token de serviço não abre notebook, o portão pede sessão).

Regras do portão que vivem aqui:
 * 401 sem sessão (a fábrica autenticado resolve);
 * 404 para slug de OUTRO inquilino (não confirma a existência do notebook alheio);
 * o contêiner sobe sob demanda na primeira passagem e cada uso de API marca ociosidade
   (plat.notebook_uso.ultimo_uso — o ceifador mede por aí).

WebSocket do kernel é bombeado nos dois sentidos (websockets.asyncio.client para o contêiner).
O tráfego do Jupyter NUNCA gera evento de domínio da plataforma (proxy transparente); evento
só na execução agendada (notebooks/executado, app/notebooks/tarefas.py).
"""

import asyncio
import threading

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocket

from app.auth.sessao import Auth, autenticado, resolver
from app.erros import ErroAPI
from app.notebooks import config, contenedor

router = APIRouter(tags=["notebooks"])
X = {"x-auth": "S", "x-privilegio": "proprio"}

# cabeçalhos que não atravessam proxy (RFC 7230 6.1) — nos dois sentidos
SALTOS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
          "te", "trailer", "transfer-encoding", "upgrade"}

_vivos: dict[str, bool] = {}  # cache por processo: slug -> contêiner já visto de pé
_cliente: httpx.AsyncClient | None = None
_TRAVA_CLIENTE = threading.Lock()


def _http() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None or _cliente.is_closed:
        with _TRAVA_CLIENTE:
            if _cliente is None or _cliente.is_closed:
                _cliente = httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(60.0))
    return _cliente


def _slug_ou_404(auth: Auth, slug: str) -> str:
    """Slug de URL só bate com o inquilino da sessão; outro slug é 404 (não 403, para não
    confirmar que o notebook do outro inquilino existe)."""
    if slug != auth.tenant_slug:
        raise ErroAPI(404, "nao_encontrado", "recurso inexistente")
    return slug


def _cabecalhos(d: object, extra: dict | None = None) -> dict:
    saida = {}
    for chave, valor in d.items():
        if chave.lower() in SALTOS or chave.lower() == "host":
            continue
        saida[chave] = valor
    if extra:
        saida.update(extra)
    return saida


async def _levantar_se_preciso(auth: Auth, slug: str) -> None:
    """Levanta o contêiner se este processo ainda não sabe que ele está de pé; se mesmo assim
    um pedido levar 502 (morreu na hora), o chamador esquece o slug e a passagem seguinte
    reergue."""
    if _vivos.get(slug):
        return
    await run_in_threadpool(contenedor.levantar, slug, auth.contexto())
    _vivos[slug] = True


async def _tocar(auth: Auth, caminho: str) -> None:
    """Ociosidade conta uso de API do Jupyter (abas estáticas não mantêm ninguém vivo)."""
    if caminho.startswith("api/") or caminho.startswith("/api/"):
        await run_in_threadpool(contenedor.tocar, auth.contexto())


@router.get("/notebooks/{slug}", openapi_extra=X)
def abrir(slug: str, auth: Auth = autenticado(so_sessao=True)):
    _slug_ou_404(auth, slug)
    return RedirectResponse(f"/notebooks/{slug}/lab", status_code=307)


@router.get("/notebooks/{slug}/", openapi_extra=X)
def abrir_barra(slug: str, auth: Auth = autenticado(so_sessao=True)):
    _slug_ou_404(auth, slug)
    return RedirectResponse(f"/notebooks/{slug}/lab", status_code=307)


async def proxy(slug: str, caminho: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    _slug_ou_404(auth, slug)
    await _levantar_se_preciso(auth, slug)
    await _tocar(auth, caminho)
    cfg = config.obter()
    nome = config.nome_contenedor(slug)
    ip = await run_in_threadpool(contenedor._ip, nome, cfg)
    if not ip:
        # o contêiner morreu por fora (ceifador do worker, docker stop) e o cache deste
        # processo ainda o acha de pé: esquece e reergue NA MESMA passagem — o "volta na
        # próxima passagem" do portão, sem 502 na cara de quem só estava usando o notebook
        _vivos.pop(slug, None)
        await _levantar_se_preciso(auth, slug)
        ip = await run_in_threadpool(contenedor._ip, nome, cfg)
    if not ip:
        # sem IP não há para onde mandar o pedido; pior, "http://:8888/..." (host vazio) é
        # URL relativo para o httpx, que o reescreve no merge e estoura ValueError 500
        # (medido na suíte) em vez do 502 honesto
        raise ErroAPI(502, "notebook_fora", "notebook não está respondendo; tente de novo")
    url = f"http://{ip}:8888{config.base_url(slug)}{caminho}"
    if request.url.query:
        url += "?" + request.url.query
    corpo = await request.body()
    try:
        resposta = await _http().request(
            request.method, url,
            headers=_cabecalhos(request.headers, {"host": f"{ip}:8888"}),
            content=corpo,
        )
    except httpx.HTTPError:
        _vivos.pop(slug, None)
        raise ErroAPI(502, "notebook_fora", "notebook não está respondendo; tente de novo") from None
    return Response(
        content=resposta.content,
        status_code=resposta.status_code,
        headers=_cabecalhos(resposta.headers),
        background=None,
    )


# Um endpoint, cinco métodos: rota única com methods=[...] deixava os 5 operationId iguais no
# OpenAPI ("Duplicate Operation ID ...proxy...patch", medido ao gerar docs/openapi.json) — cada
# registro tem nome próprio, e o operationId segue o nome.
for _metodo in ("GET", "POST", "PUT", "PATCH", "DELETE"):
    router.add_api_route(
        "/notebooks/{slug}/{caminho:path}", proxy, methods=[_metodo],
        name=f"notebook_proxy_{_metodo.lower()}", openapi_extra=X,
    )


@router.websocket("/notebooks/{slug}/{caminho:path}")
async def proxy_ws(websocket: WebSocket, slug: str, caminho: str):
    """Canal do kernel (api/kernels/*/channels): sessão válida + slug do próprio inquilino;
    fecha 4401 sem sessão, 4404 para slug alheio (mesma semântica do HTTP)."""
    try:
        auth = resolver(websocket)
    except ErroAPI:
        auth = None
    if auth is None:
        await websocket.close(code=4401)
        return
    if slug != auth.tenant_slug:
        await websocket.close(code=4404)
        return
    try:
        await _levantar_se_preciso(auth, slug)
        await _tocar(auth, caminho)
    except ErroAPI as e:
        await websocket.close(code=4404 if e.status == 404 else 1013)
        return
    cfg = config.obter()
    nome = config.nome_contenedor(slug)
    ip = await run_in_threadpool(contenedor._ip, nome, cfg)
    consulta = websocket.url.query
    destino = f"ws://{ip}:8888{config.base_url(slug)}{caminho}"
    if consulta:
        destino += "?" + consulta
    import websockets.asyncio.client

    cookie = websocket.headers.get("cookie", "")
    try:
        ws_destino = await websockets.asyncio.client.connect(
            destino, additional_headers={"Cookie": cookie} if cookie else {}, max_size=None,
        )
    except Exception:
        _vivos.pop(slug, None)
        await websocket.close(code=1013)
        return
    await websocket.accept()

    async def para_dentro():
        try:
            while True:
                dado = await websocket.receive()
                if dado.get("type") == "websocket.disconnect":
                    break
                if "bytes" in dado and dado["bytes"] is not None:
                    await ws_destino.send(dado["bytes"])
                elif "text" in dado and dado["text"] is not None:
                    await ws_destino.send(dado["text"])
        except Exception:
            pass

    async def para_fora():
        try:
            while True:
                dado = await ws_destino.recv()
                if isinstance(dado, bytes):
                    await websocket.send_bytes(dado)
                else:
                    await websocket.send_text(dado)
        except Exception:
            pass

    try:
        tarefa_dentro = asyncio.create_task(para_dentro())
        tarefa_fora = asyncio.create_task(para_fora())
        feito, pendentes = await asyncio.wait({tarefa_dentro, tarefa_fora},
                                              return_when=asyncio.FIRST_COMPLETED)
        for t in pendentes:
            t.cancel()
        _ = feito
    finally:
        try:
            await ws_destino.close()
        except Exception:
            pass
