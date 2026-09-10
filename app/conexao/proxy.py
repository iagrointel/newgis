"""Proxy de tile/imagem por CONEXÃO CADASTRADA (item L6-02-conectores-vivos): generaliza
`app/mapa/proxy_wms.py` de hoje — ali a allowlist é uma lista FIXA de 3 serviços escrita em
`app.settings.WMS_PUBLICO_ALLOWLIST`; aqui a allowlist é "as conexões que o inquilino cadastrou" em
`plat.conexao` (RLS: o `id` de outro inquilino já dá 404 antes de qualquer requisição sair). `proxy_wms.py`
continua intocado e continua servindo o navegador sem sessão — este módulo é OUTRA rota, exige sessão.

Só wms/wmts/esri_rest têm operação de tile/imagem (`limites.CONEXAO_PROXY_TIPOS`) — wfs/ogc_api são API de
feição (GeoJSON/GML por página), não raster; o conector delas é `L6-02-c` (cópia para PostGIS), não este
proxy. Mesmo cuidado do proxy público: allowlist de REQUEST (wms/wmts), timeout curto, teto de bytes, cache —
mas aqui todo GET passa por `app.conexao.seguranca.buscar_seguro` (SSRF pinado, nunca `httpx` direto), porque
a URL vem de uma tabela que o PRÓPRIO usuário escreveu (a defesa de SSRF já correu uma vez na entrada,
`app.conexao.rotas._url_ok`; aqui corre de novo, porque uma URL seguro-quando-cadastrada pode passar a
resolver para um IP interno mais tarde — DNS rebinding, o caso 8 da docstring de `seguranca.py`)."""

from __future__ import annotations

import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import uuid_ok
from app.conexao import credencial as credencial_mod
from app.conexao import seguranca
from app.erros import ErroAPI
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

log = logging.getLogger("plat.conexao.proxy")
router = APIRouter(prefix="/api/conexoes", tags=["conexoes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}

_REQUEST_PERMITIDO = {"wms": {"GETMAP", "GETCAPABILITIES"}, "wmts": {"GETTILE", "GETCAPABILITIES"}}

# cache em processo (mesma ideia do comentário de proxy_wms.py: o nginx da instalação real cacheia por cima;
# isto aqui evita bater no serviço externo de novo dentro do mesmo processo, mesma janela de 10 min). Chave
# inclui o id da conexão: duas conexões nunca compartilham entrada, mesmo que a URL final coincida.
_CACHE: dict[str, tuple[float, int, str, bytes]] = {}


def _cache_pegar(chave: str) -> tuple[int, str, bytes] | None:
    item = _CACHE.get(chave)
    if item is None:
        return None
    expira_em, status, tipo, corpo = item
    if expira_em < time.monotonic():
        _CACHE.pop(chave, None)
        return None
    return status, tipo, corpo


def _cache_guardar(chave: str, status: int, tipo: str, corpo: bytes) -> None:
    if len(_CACHE) >= limites.CONEXAO_PROXY_CACHE_MAX_ITENS:
        # LRU simples por ordem de inserção (dict do Python preserva a ordem): tira o mais antigo, não o
        # maior nem o menos usado — barato e suficiente para um cache de minutos, não de política de negócio.
        _CACHE.pop(next(iter(_CACHE)), None)
    _CACHE[chave] = (time.monotonic() + limites.CONEXAO_PROXY_CACHE_TTL_S, status, tipo, corpo)


def _mesclar_query(url_base: str, novos: dict[str, str]) -> str:
    """Funde a querystring já presente na URL cadastrada com os parâmetros do pedido — `buscar_seguro` só
    aceita uma URL pronta (não um par url+params como `httpx.AsyncClient.get`), então a fusão é manual aqui.
    Em empate de chave (case-insensitive não considerado de propósito: WMS é sensível a maiúscula em alguns
    GeoServers), o parâmetro do PEDIDO vence — é o que o navegador quer ver."""
    partes = urlsplit(url_base)
    existentes = dict(parse_qsl(partes.query, keep_blank_values=True))
    existentes.update(novos)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(existentes), partes.fragment))


def _carregar_para_proxy(cur, cid: str) -> dict:
    cur.execute("SELECT tipo, url, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        # RLS já filtrou por tenant_id antes daqui: conexão de outro inquilino cai neste MESMO 404, sem
        # distinção de "existe mas não é sua" — nunca revela a existência de um id alheio.
        raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
    return r


def _url_alvo(tipo: str, url_base: str, parametros: dict[str, str]) -> str:
    if tipo in ("wms", "wmts"):
        pedido = next((v for k, v in parametros.items() if k.upper() == "REQUEST"), None)
        permitidos = _REQUEST_PERMITIDO[tipo]
        if not pedido or pedido.upper() not in permitidos:
            raise ErroAPI(
                422, "request_nao_permitido",
                f"só REQUEST={'/'.join(sorted(permitidos))} é repassado neste tipo de conexão",
            )
        return _mesclar_query(url_base, parametros)
    # esri_rest: operação `export` de MapServer/ImageServer (a única do REST API que devolve uma IMAGEM
    # pronta, o equivalente ao GetMap do WMS); `f` é sempre forçado para `image` — o pedido não escolhe JSON
    # aqui (a rota é de tile/imagem, não de metadado; metadado é a descoberta, `POST /descobrir`).
    base = url_base.rstrip("/")
    if not base.lower().endswith("/export"):
        base = f"{base}/export"
    forcados = dict(parametros)
    forcados["f"] = "image"
    return _mesclar_query(base, forcados)


@router.get("/{id}/tile", openapi_extra=LER)
def tile(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar_para_proxy(cur, cid)

    tipo = r["tipo"]
    if tipo not in limites.CONEXAO_PROXY_TIPOS:
        raise ErroAPI(
            422, "tipo_sem_proxy",
            f"conexão do tipo {tipo!r} não tem proxy de tile/imagem (só {', '.join(limites.CONEXAO_PROXY_TIPOS)})",
        )

    parametros = dict(request.query_params)
    alvo = _url_alvo(tipo, r["url"], parametros)

    chave = f"{cid}:{alvo}"
    em_cache = _cache_pegar(chave)
    if em_cache is not None:
        status, tipo_conteudo, corpo = em_cache
        return Response(
            content=corpo, status_code=status, media_type=tipo_conteudo,
            headers={"Cache-Control": f"public, max-age={limites.CONEXAO_PROXY_CACHE_TTL_S}", "X-Plat-Cache": "hit"},
        )

    # credencial decifrada só em memória, só para autenticar ESTA busca (mesmo padrão de app/conexao/rotas.py::testar)
    cabecalhos = None
    if r["credencial_cifrada"]:
        try:
            token = decifrar_com_rotacao(
                credencial_mod.decifrar, r["credencial_cifrada"], settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
            )
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except Exception:  # noqa: BLE001 — segredo trocado/dado corrompido: tenta sem credencial, nunca quebra a rota
            cabecalhos = None

    resultado = seguranca.buscar_seguro(
        alvo, timeout_conectar=limites.CONEXAO_PROXY_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.CONEXAO_PROXY_LER_TIMEOUT_S,
        max_bytes=limites.CONEXAO_PROXY_MAX_BYTES, cabecalhos=cabecalhos, guardar_corpo=True,
    )
    if not resultado.ok:
        log.warning("proxy de tile: conexao=%s tipo=%s alvo=%s falhou: %s", cid, tipo, alvo, resultado.mensagem)
        raise ErroAPI(502, "tile_indisponivel", f"o serviço externo não respondeu ({resultado.mensagem})")

    status = resultado.status or 200
    tipo_conteudo = resultado.content_type or "application/octet-stream"
    _cache_guardar(chave, status, tipo_conteudo, resultado.corpo)
    return Response(
        content=resultado.corpo, status_code=status, media_type=tipo_conteudo,
        headers={"Cache-Control": f"public, max-age={limites.CONEXAO_PROXY_CACHE_TTL_S}", "X-Plat-Cache": "miss"},
    )
