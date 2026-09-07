"""Diretório de serviços compatível com Esri, escopado por token no CAMINHO (item L2-04-b).

Por que o token vai no caminho e não no cabeçalho: os clientes que interessam aqui — QGIS pelo
conector "ArcGIS REST Server", ArcGIS Pro, o `arcgis` do Python, visualizadores embutidos — pedem
UMA raiz de serviços e navegam sozinhos a partir dela. Quem entrega essa raiz é o operador, colando
uma URL. Uma URL com o token dentro (`/svc/<token>/rest/services`) navega inteira; um cabeçalho
`Authorization` não sobrevive a copiar e colar. É o mesmo desenho que o `?token=` do protocolo Esri
já pressupõe (`rotas_query._autenticar` aceita as duas formas desde o item L2-04-c).

A consequência de segurança está declarada: quem tem a URL tem o acesso do token, e por isso o token
nasce com escopo de leitura e validade curta (`generateToken`, teto de 24 h), e o diretório mostra
SÓ o que o inquilino daquele token pode ler — a segregação não é filtro de aplicação, é a RLS do
banco (`db.db(auth.contexto())`), a mesma do resto da plataforma.

O que este módulo NÃO faz: reimplementar o FeatureServer. O descritor do serviço, o da camada e a
operação `query` são os do item L2-04-servicos-esri-ogc/L2-04-c (`rotas_servico`, `rotas_query`),
chamados aqui como funções. Este módulo acrescenta o que faltava para um cliente DESCOBRIR o
serviço sem saber o UUID de antemão: `rest/info`, `rest/generateToken`, a árvore de pastas em
`rest/services`, `/layers`, `/info/itemInfo`, `/info/metadata`, e a negociação `f`/`callback`.

Referência: developers.arcgis.com, "Get started with the services directory", "Feature service",
"Layer (Feature Service)" e "Generate token"."""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Request, Response

from app import db
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.auth.politica import HASH_FANTASMA
from app.consulta import rotas_query, rotas_servico
from app.consulta.formato_esri import resposta_esri
from app.erros import ErroAPI
from app.senha import verificar as verificar_senha

router = APIRouter(tags=["consulta-esri"])
RAIZ = "/svc/{token}/rest"
SERVICOS = f"{RAIZ}/services"
LER = {"x-auth": "T", "x-privilegio": "proprio"}
PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}
CURRENT_VERSION = rotas_servico.CURRENT_VERSION
# teto da cláusula do item: um token gerado por usuário/senha vale no máximo 24 h
GERADO_MINUTOS_MAX = 24 * 60
GERADO_MINUTOS_PADRAO = 60
GERADO_ESCOPOS = ["catalogo:ler", "camada:ler", "tiles:ler"]
_PASTA_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,120}$")
SEM_PASTA = "SemPasta"


def _f(request: Request) -> tuple[str | None, str | None]:
    p = request.query_params
    return p.get("f"), p.get("callback")


def _auth_do_caminho(request: Request, token: str, item_id: str | None = None):
    """O token do CAMINHO é a credencial. Reusa `_auth_de_token` (mesma verificação de hash,
    expiração, revogação e restrição de referer/IP do resto da plataforma) e exige o escopo de
    leitura; nunca aceita sessão de navegador aqui, para que a URL do diretório valha por si."""
    auth = auth_sessao._auth_de_token(request, token)  # noqa: SLF001 — mesmo reuso do GeocodeServer
    request.state.auth = auth
    esc.exigir_escopo(auth, "catalogo:ler")
    if item_id is not None:
        esc.exigir_escopo(auth, rotas_query.ESCOPO, item_id)
    return auth


def _url_base(request: Request, token: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/svc/{token}/rest"


def _camadas_visiveis(cur) -> list[dict]:
    """Itens de camada vetorial que a RLS deixa este token enxergar, com a pasta do catálogo.
    `plat.item` só devolve o que o inquilino do contexto pode ler — a segregação é do banco."""
    cur.execute(
        "SELECT i.id, i.titulo, i.resumo, i.descricao, i.tags, i.dados, i.pasta_id, p.nome AS pasta "
        "FROM plat.item i LEFT JOIN plat.pasta p ON p.id = i.pasta_id "
        "WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL "
        "ORDER BY p.nome NULLS FIRST, i.titulo"
    )
    return cur.fetchall()


def _nome_pasta(r: dict) -> str:
    nome = (r["pasta"] or "").strip()
    return nome if nome and _PASTA_RE.match(nome) else SEM_PASTA


def _servico(r: dict, prefixo_pasta: str) -> dict:
    return {"name": f"{prefixo_pasta}{r['id']}", "type": "FeatureServer"}


# ------------------------------------------------------------------ rest/info e generateToken
@router.get(f"{RAIZ}/info", openapi_extra=PUBLICO, operation_id="svc_rest_info")
@router.post(f"{RAIZ}/info", openapi_extra=PUBLICO, operation_id="svc_rest_info_post")
def rest_info(token: str, request: Request):
    """`rest/info` é o primeiro pedido de todo cliente Esri e NÃO exige credencial válida (é onde o
    cliente descobre como se autenticar). Não revela nada do inquilino: só versão e para onde mandar
    usuário/senha. O token do caminho é ecoado apenas dentro da URL do serviço de token."""
    base = _url_base(request, token)
    f, cb = _f(request)
    return resposta_esri({
        "currentVersion": CURRENT_VERSION,
        "fullVersion": f"{CURRENT_VERSION}.0",
        "owningSystemUrl": base.rsplit("/rest", 1)[0],
        "authInfo": {
            "isTokenBasedSecurity": True,
            "tokenServicesUrl": f"{base}/generateToken",
            "shortLived": True,
            "tokenExpirationMinutesMax": GERADO_MINUTOS_MAX,
        },
    }, f, cb)


async def _credenciais(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        tipo = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in tipo or "multipart/form-data" in tipo:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in tipo:
            corpo = await request.json()
            if isinstance(corpo, dict):
                p.update({k: str(v) for k, v in corpo.items()})
    return p


def _erro_esri(codigo: int, mensagem: str, detalhe: str) -> dict:
    """O protocolo Esri devolve erro com HTTP 200 e o código dentro do corpo; é assim que o cliente
    distingue "senha errada" de "servidor caiu"."""
    return {"error": {"code": codigo, "message": mensagem, "details": [detalhe]}}


@router.get(f"{RAIZ}/generateToken", openapi_extra=PUBLICO, operation_id="svc_generate_token_get")
@router.post(f"{RAIZ}/generateToken", openapi_extra=PUBLICO, operation_id="svc_generate_token")
async def generate_token(token: str, request: Request):
    """Troca usuário/senha do inquilino por um token de SERVIÇO de leitura, com validade de no
    máximo 24 h (`expiration` em minutos, teto aplicado sem reclamar, como faz o ArcGIS Server).

    O inquilino é o do token que está no caminho — não se pede o slug de novo, e um usuário de outro
    inquilino não autentica aqui nem por acaso. Conta com 2FA ligado é recusada com o código 400 do
    protocolo: `generateToken` não tem onde pedir o segundo fator, e aceitar só a senha rebaixaria a
    política do inquilino."""
    portador = _auth_do_caminho(request, token)
    p = await _credenciais(request)
    usuario = (p.get("username") or "").strip()
    senha_dada = p.get("password") or ""
    if not usuario or not senha_dada:
        return resposta_esri(_erro_esri(400, "Unable to generate token.",
                                       "informe username e password"), p.get("f"), p.get("callback"))
    minutos = _minutos(p.get("expiration"))
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (portador.tenant_slug, usuario))
        r = cur.fetchone()
    negado = resposta_esri(_erro_esri(400, "Unable to generate token.",
                                      "usuário ou senha inválidos"), p.get("f"), p.get("callback"))
    if r is None or not r["ativo"] or not r["ativo_tenant"] or r["origem"] != "local":
        verificar_senha(senha_dada, HASH_FANTASMA)  # mesmo custo do caminho certo (tempo constante)
        return negado
    if not verificar_senha(senha_dada, r["senha_hash"] or HASH_FANTASMA):
        return negado
    if r["totp_ativo"]:
        return resposta_esri(
            _erro_esri(400, "Unable to generate token.",
                       "esta conta usa segundo fator; gere o token pela API /api/tokens"),
            p.get("f"), p.get("callback"))
    ctx = db.Contexto(r["tenant_id"], r["usuario_id"], usuario.lower())
    valor = "plat_" + secrets.token_urlsafe(32)
    with db.db(ctx) as cur:
        cur.execute(
            "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, "
            "restricao, expira_em) VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, "
            "now() + make_interval(mins => %s)) RETURNING expira_em",
            (r["tenant_id"], r["usuario_id"], f"generateToken {usuario}", auth_sessao.sha256_hex(valor),
             valor[:12], GERADO_ESCOPOS, minutos),
        )
        expira = cur.fetchone()["expira_em"]
    return resposta_esri({
        "token": valor,
        "expires": int(expira.timestamp() * 1000),
        "ssl": request.url.scheme == "https",
        "scopes": GERADO_ESCOPOS,
    }, p.get("f"), p.get("callback"))


def _minutos(valor) -> int:
    try:
        m = int(str(valor))
    except (TypeError, ValueError):
        return GERADO_MINUTOS_PADRAO
    return min(max(m, 1), GERADO_MINUTOS_MAX)


# ------------------------------------------------------------------ árvore de serviços
@router.get(SERVICOS, openapi_extra=LER, operation_id="svc_servicos_raiz")
def servicos_raiz(token: str, request: Request):
    """Raiz do catálogo: pastas (as do catálogo do inquilino) e os serviços da raiz. Um FeatureServer
    por camada vetorial legível — é o que o QGIS lista ao conectar."""
    auth = _auth_do_caminho(request, token)
    f, cb = _f(request)
    with db.db(auth.contexto()) as cur:
        linhas = _camadas_visiveis(cur)
    pastas = sorted({_nome_pasta(r) for r in linhas if _nome_pasta(r) != SEM_PASTA})
    servicos = [_servico(r, "") for r in linhas if _nome_pasta(r) == SEM_PASTA]
    return resposta_esri({
        "currentVersion": CURRENT_VERSION,
        "folders": pastas,
        "services": servicos,
    }, f, cb)


@router.get(f"{SERVICOS}/{{pasta}}", openapi_extra=LER, operation_id="svc_servicos_pasta")
def servicos_pasta(token: str, pasta: str, request: Request):
    auth = _auth_do_caminho(request, token)
    f, cb = _f(request)
    with db.db(auth.contexto()) as cur:
        linhas = [r for r in _camadas_visiveis(cur) if _nome_pasta(r) == pasta]
    if not linhas:
        raise ErroAPI(404, "pasta_nao_encontrada", "pasta inexistente ou sem camada legível por este token")
    return resposta_esri({
        "currentVersion": CURRENT_VERSION,
        "folders": [],
        "services": [_servico(r, f"{pasta}/") for r in linhas],
    }, f, cb)


# ------------------------------------------------------------------ FeatureServer sob o token
def _descritor_servico(request: Request, token: str, item_id: str) -> dict:
    auth = _auth_do_caminho(request, token, item_id)
    return rotas_servico.montar_descritor_servico(auth, item_id)


@router.get(f"{SERVICOS}/{{item_id}}/FeatureServer", openapi_extra=LER,
            operation_id="svc_featureserver_raiz")
def featureserver(token: str, item_id: str, request: Request):
    f, cb = _f(request)
    return resposta_esri(_descritor_servico(request, token, item_id), f, cb)


@router.get(f"{SERVICOS}/{{item_id}}/FeatureServer/layers", openapi_extra=LER,
            operation_id="svc_featureserver_layers")
def featureserver_layers(token: str, item_id: str, request: Request):
    """`/layers` devolve os descritores COMPLETOS de camadas e tabelas de uma vez — é o pedido que o
    ArcGIS Pro faz para desenhar a legenda sem N idas ao servidor."""
    auth = _auth_do_caminho(request, token, item_id)
    f, cb = _f(request)
    return resposta_esri(rotas_servico.montar_layers(auth, item_id), f, cb)


@router.get(f"{SERVICOS}/{{item_id}}/FeatureServer/info/itemInfo", openapi_extra=LER,
            operation_id="svc_featureserver_iteminfo")
def featureserver_item_info(token: str, item_id: str, request: Request):
    auth = _auth_do_caminho(request, token, item_id)
    f, cb = _f(request)
    return resposta_esri(rotas_servico.montar_item_info(auth, item_id), f, cb)


@router.get(f"{SERVICOS}/{{item_id}}/FeatureServer/info/metadata", openapi_extra=LER,
            operation_id="svc_featureserver_metadata")
def featureserver_metadata(token: str, item_id: str, request: Request):
    """Metadado no perfil ISO 19139, que é o que o ArcGIS Pro e o QGIS pedem neste caminho — XML,
    não JSON: aqui `f` não se aplica."""
    auth = _auth_do_caminho(request, token, item_id)
    return Response(rotas_servico.montar_metadata_iso(auth, item_id), media_type="text/xml; charset=utf-8")


@router.get(f"{SERVICOS}/{{item_id}}/FeatureServer/{{camada_id}}", openapi_extra=LER,
            operation_id="svc_featureserver_camada")
def featureserver_camada(token: str, item_id: str, camada_id: str, request: Request):
    auth = _auth_do_caminho(request, token, item_id)
    f, cb = _f(request)
    return resposta_esri(rotas_servico.montar_descritor_camada(auth, item_id, camada_id), f, cb)
