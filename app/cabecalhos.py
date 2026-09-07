"""Cabeçalhos de segurança por resposta (item L7-03-e).

Uma origem só para cada cabeçalho, pela mesma razão já registrada em T2 para o Cache-Control: `add_header`
do nginx ACRESCENTA, nunca substitui, então cabeçalho posto nos dois lugares sai duplicado e o serviço não
tem como se opor ao valor do proxy. A repartição é:

* a APLICAÇÃO declara o que depende da resposta: Content-Security-Policy (com nonce por resposta e
  `frame-ancestors` por inquilino), Permissions-Policy, Cross-Origin-Opener-Policy,
  Cross-Origin-Resource-Policy, Referrer-Policy, X-Content-Type-Options e o CORS por token;
* o NGINX declara o que depende do transporte e do que ele mesmo serve: Strict-Transport-Security,
  X-Robots-Tag e, em `/static/`, o conjunto inteiro (lá o nginx é a origem do corpo).

`X-Frame-Options` sai da aplicação de propósito: quem manda no embutir é `frame-ancestors`, que os
navegadores atuais aplicam com precedência sobre o cabeçalho antigo e, ao contrário dele, aceita uma
LISTA de origens — que é o caso de uso (embutir o mapa no sítio do cliente). Ver docs/SEGURANCA.md.
"""

import json
import secrets
import time

from fastapi import FastAPI, Request
from starlette.responses import Response

from app import db
from app.auth.sessao import origem_permitida

# Permissions-Policy: tudo desligado menos a localização, que o mapa usa ("onde estou") na própria origem.
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), encrypted-media=(), fullscreen=(self), "
    "geolocation=(self), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), "
    "picture-in-picture=(), publickey-credentials-get=(), screen-wake-lock=(), usb=(), xr-spatial-tracking=()"
)
REFERRER_POLICY = "strict-origin-when-cross-origin"
# Documento HTML: script só da própria origem ou com o nonce da resposta (a Swagger UI é servida do disco,
# sem CDN); `blob:` em worker/child porque o MapLibre cria o seu worker por blob URL.
CSP_DOCUMENTO = (
    "default-src 'self'",
    "script-src 'self' 'nonce-{nonce}'",
    "style-src 'self'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "child-src 'self' blob:",
    "media-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-src 'self'",
    "upgrade-insecure-requests",
)
# Tudo que não é documento (JSON, GeoJSON, imagem, tile, arquivo): nada pode ser carregado a partir dele.
CSP_DADO = ("default-src 'none'", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'")
CORS_VERBOS = "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS"
CORS_CABECALHOS = "authorization, content-type, x-requested-with"
CORS_EXPOSTOS = "x-req-id"
CORS_MAX_AGE = "600"
CACHE_ORIGENS_S = 60.0
_cache_origens: dict[tuple[str, str], tuple[float, tuple[str, ...]]] = {}


def _do_banco(slug: str | None, tenant_id: int | None) -> tuple[str, ...]:
    """`config -> 'origens_embutidas'` do inquilino, por id ou por slug, pela função SECURITY DEFINER da
    migração 20260907T2047 (o middleware roda antes de haver contexto de inquilino na conexão). Erro de
    banco = lista vazia: cabeçalho de segurança nunca derruba resposta, e a falta dele FECHA."""
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.origens_embutidas(%s, %s) AS origens", (slug, tenant_id))
            linha = cur.fetchone()
    except Exception:  # noqa: BLE001 — ver docstring
        return ()
    if not linha:
        return ()
    origens = linha["origens"]
    if isinstance(origens, str):
        origens = json.loads(origens)
    return tuple(o for o in (origens or []) if isinstance(o, str))


def origens_embutidas(request: Request) -> tuple[str, ...]:
    """Origens que podem embutir as páginas deste inquilino. O inquilino vem da autenticação da própria
    requisição (state.tenant_id) ou, nas páginas que ainda não têm sessão, do parâmetro `inquilino`."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is not None:
        chave = ("id", str(tenant_id))
    else:
        slug = (request.query_params.get("inquilino") or "").strip().lower()
        if not slug or not slug.replace("-", "").isalnum():
            return ()
        chave = ("slug", slug)
    agora = time.monotonic()
    guardado = _cache_origens.get(chave)
    if guardado is not None and guardado[0] > agora:
        return guardado[1]
    origens = _do_banco(None, int(chave[1])) if chave[0] == "id" else _do_banco(chave[1], None)
    _cache_origens[chave] = (agora + CACHE_ORIGENS_S, origens)
    return origens


def esquecer_origens() -> None:
    """Zera o cache de origens (usado pelos testes e por quem acabou de gravar a configuração)."""
    _cache_origens.clear()


def politica(request: Request, resposta: Response, nonce: str) -> str:
    tipo = (resposta.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo not in ("text/html", "application/xhtml+xml"):
        return "; ".join(CSP_DADO)
    origens = origens_embutidas(request)
    ancestrais = "frame-ancestors " + (" ".join(("'self'", *origens)) if origens else "'none'")
    return "; ".join(d.format(nonce=nonce) for d in CSP_DOCUMENTO) + "; " + ancestrais


def _origem_de_token_permitida(request: Request, origem: str) -> bool:
    """CORS por token: a lista de origens é a MESMA `restricao.referer` que app/auth/sessao.py já exige
    para o token ser aceito (item L0-02). Se a requisição chegou aqui com token_id, a origem já passou
    naquela verificação — este trecho só repete a comparação para não ecoar origem de token sem lista."""
    restricao = getattr(request.state, "token_restricao", None) or {}
    permitidas = restricao.get("referer") or []
    return bool(permitidas) and origem_permitida(origem, permitidas)


def _cors(request: Request, resposta: Response) -> None:
    origem = request.headers.get("origin")
    if not origem:
        return
    resposta.headers.setdefault("Vary", "Origin")
    if not _origem_de_token_permitida(request, origem):
        return
    resposta.headers["Access-Control-Allow-Origin"] = origem
    resposta.headers["Access-Control-Expose-Headers"] = CORS_EXPOSTOS
    resposta.headers["Cross-Origin-Resource-Policy"] = "cross-origin"


def _preflight(request: Request) -> Response | None:
    """Resposta ao CORS preflight. O navegador manda OPTIONS SEM o token (a especificação proíbe crachá
    no preflight), então não há como decidir aqui pela lista do token: o preflight só autoriza o método e
    os cabeçalhos, e a requisição de verdade continua barrada pela restrição do token (401
    referer_nao_permitido). Autorizar o preflight não entrega dado nenhum."""
    if request.method != "OPTIONS" or "origin" not in request.headers:
        return None
    if "access-control-request-method" not in request.headers:
        return None
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": request.headers["origin"],
            "Access-Control-Allow-Methods": CORS_VERBOS,
            "Access-Control-Allow-Headers": CORS_CABECALHOS,
            "Access-Control-Max-Age": CORS_MAX_AGE,
            "Vary": "Origin",
            "Cache-Control": "no-store, must-revalidate",
        },
    )


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def cabecalhos(request: Request, call_next):
        nonce = secrets.token_urlsafe(18)
        request.state.csp_nonce = nonce
        resposta = _preflight(request) or await call_next(request)
        resposta.headers["Content-Security-Policy"] = politica(request, resposta, nonce)
        resposta.headers["Referrer-Policy"] = REFERRER_POLICY
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resposta.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        resposta.headers.setdefault("Cache-Control", "no-store, must-revalidate")
        _cors(request, resposta)
        return resposta
