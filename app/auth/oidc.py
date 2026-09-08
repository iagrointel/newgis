"""Login federado OpenID Connect por inquilino (item L0-08-a-oidc, irmão do L0-08-d-ldap; mesma família
L0-08-sso). Módulo isolado no padrão de app/auth/ldap.py: valida a identidade no provedor externo e REAPROVEITA
`_abrir_sessao` (app/auth/rotas_login.py) a partir daí — cookie, evento `usuarios/entrar` e política de sessão
são os do login local, nunca um segundo caminho. Um inquilino pode ter mais de um provedor (vários botões).

Fluxo (Authorization Code + PKCE S256, RFC 7636; descoberta OIDC, RFC 8414):
  GET /api/sso/oidc/iniciar?inquilino=<slug>[&provedor_id=<id>]
      → resolve o(s) provedor(es) habilitados do inquilino, escolhe o pedido (ou o de menor `ordem`) →
        descoberta do issuer (cache com TTL) → gera state/nonce/verificador PKCE, abre a transação (uso
        único, TTL 10 min, plat.oidc_transacao) → 302 para o authorization_endpoint do IdP.
  GET /api/sso/oidc/retorno?code&state
      → consome a transação (DELETE...RETURNING atômico: reenviar o MESMO state duas vezes só funciona uma
        vez) → troca o código no token_endpoint (com o verificador PKCE, nunca sem) → valida o id_token
        (assinatura via JWKS do issuer configurado — nunca outro; issuer, audience = client_id deste
        provedor, nonce da transação, exp/iat com folga) → claim de identificador de login É 'sub' (estável;
        mudar depois quebraria as contas, como a doc Esri avisa — nunca email) → mapeia grupos→perfil →
        provisiona (plat.oidc_provisionar; conta 'oidc' nunca tem senha nem TOTP local) → `_abrir_sessao`.
  GET /api/sso/oidc/logout
      → encerra a sessão LOCAL sempre (mesmo caminho de app.auth.rotas_login.logout) e, quando a conta é
        'oidc' e o provedor publica `end_session_endpoint`, devolve também a URL de logout do IdP (RP-Initiated
        Logout, OIDC Session Management) para o front completar a propagação — o portão do item ("logout
        propagado") é a soma das duas pontas, nunca só o cookie local.

Chaves de segurança, na ordem em que a refutação do item as testa:
  1. `code_verifier`/PKCE: sem ele o token_endpoint recusa (código roubado por um segundo cliente não vale
     nada sem o verificador que só o navegador que iniciou o fluxo tem);
  2. `state`: comparado por posse de linha na transação (DELETE...RETURNING de uso único) — trocar o state
     não aponta para transação nenhuma, 401 antes de qualquer troca de código;
  3. `nonce`: gravado na transação na ida, conferido no id_token na volta — id_token de uma sessão de login
     diferente (nonce certo, mas de outra transação) nunca casa com a transação que o state resolveu;
  4. `iss`/`aud`: id_token de outro client_id ou outro provedor (`aud` de outro inquilino) é recusado mesmo
     com assinatura válida — a chave pública de um provedor nunca valida o token de outro cliente por
     coincidência de emissor, e o aud errado é conferido À PARTE da assinatura.
Nenhuma dessas checagens aparece na tela: o motivo específico só vai para o log (`log.warning`); o cliente
recebe sempre o mesmo 401 genérico ("token_invalido") — o mesmo desenho de app/auth/ldap.py, que nunca
distingue 'usuário inexistente' de 'senha errada' no corpo da resposta."""

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import psycopg2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from joserfc import jwt as joserfc_jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from pydantic import Field

from app import db
from app.auth import govbr, provisionamento
from app.auth.comum import apagar_cookie, erro_do_banco, registrar_evento
from app.auth.ldap import PERFIS_VALIDOS  # mesmo vocabulário de 4 perfis
from app.auth.modelos import Modelo, Saida
from app.auth.politica import politica_de
from app.auth.rotas_login import _abrir_sessao  # reaproveita a criação de sessão do login local; ver docstring
from app.auth.sessao import COOKIE, Auth, autenticado, resolver, sha256_hex
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.auth.oidc")
router = APIRouter(prefix="/api", tags=["login"])
PREFIXO_CIFRA = "encoidc:v1:"
ALGORITMOS_ACEITOS = ("RS256", "ES256")  # nunca 'none'/HS256 (chave simétrica seria o client_secret == falsificável)
DESCOBERTA_TTL_S = 3600
JWKS_TTL_S = 600
FOLGA_RELOGIO_S = 60
HTTP_TIMEOUT_S = 8


# ---------------------------------------------------------------- cifra do client_secret (mesmo esquema
# AES-GCM de app/auth/ldap.py/app/auth/totp.py, reimplementado aqui para o módulo ficar isolado; AAD própria
# evita reuso cruzado entre módulos — um segredo cifrado para OIDC nunca decifra como segredo LDAP).
def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"oidc-client-secret").digest()


def cifrar_client_secret(segredo: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, segredo.encode("utf-8"), b"plat-oidc-secret")
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar_client_secret(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("client_secret sem o prefixo encoidc:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], b"plat-oidc-secret").decode("utf-8")


class ErroOidc(Exception):
    """Erro de descoberta/troca/validação traduzido para 401/503 genérico; o motivo específico (qual
    cláusula falhou) só vai para `motivo_interno` — nunca para o corpo da resposta HTTP."""

    def __init__(self, motivo_interno: str):
        self.motivo_interno = motivo_interno
        super().__init__(motivo_interno)


# ---------------------------------------------------------------- descoberta (RFC 8414) e JWKS, cacheados em
# memória por issuer (a unidade sobe --workers 2; cada worker tem o seu cache — custo aceito, mesmo padrão do
# contador de força bruta do LDAP). JWKS refaz a busca sozinho quando o kid do token não está no cache (chave
# ROTACIONADA no IdP: a claúsula "cache com rotação" do item é isto, nunca um cache que nunca expira).
_TRAVA_CACHE = threading.Lock()
_CACHE_DESCOBERTA: dict[str, tuple[float, dict]] = {}
_CACHE_JWKS: dict[str, tuple[float, KeySet]] = {}


def limpar_cache() -> None:
    """Só para teste: sem isto, dois testes que reusam o mesmo issuer (ex. dois provedores diferentes com o
    MESMO Keycloak de teste) veriam o cache um do outro entre execuções da suíte."""
    with _TRAVA_CACHE:
        _CACHE_DESCOBERTA.clear()
        _CACHE_JWKS.clear()


def _url_valida_https_ou_teste(url: str) -> bool:
    partes = urlsplit(url)
    if partes.scheme == "https":
        return True
    # loopback só é aceito com PLAT_AMBIENTE != 'producao' (contêiner de teste desta máquina); a mesma regra
    # que os testes de configuração do resto da casa aplicam a "sem TLS"
    return (
        partes.scheme == "http"
        and partes.hostname in ("127.0.0.1", "localhost")
        and settings.PLAT_AMBIENTE != "producao"
    )


def descoberta(issuer: str) -> dict:
    with _TRAVA_CACHE:
        cache = _CACHE_DESCOBERTA.get(issuer)
    if cache is not None and cache[0] > time.monotonic():
        return cache[1]
    if not _url_valida_https_ou_teste(issuer):
        raise ErroOidc(f"issuer_invalido:{issuer}")
    try:
        r = httpx.get(issuer.rstrip("/") + "/.well-known/openid-configuration", timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        doc = r.json()
    except httpx.HTTPError as e:
        raise ErroOidc(f"descoberta_indisponivel:{type(e).__name__}:{e}") from e
    if doc.get("issuer") != issuer:
        # RFC 8414 §3.3: o issuer do documento tem de bater byte a byte com o que foi pedido — senão o
        # provedor está devolvendo metadado de outro emissor (ou um proxy mal configurado no meio)
        raise ErroOidc(f"issuer_divergente:{doc.get('issuer')!r}!={issuer!r}")
    for campo in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(campo):
            raise ErroOidc(f"descoberta_incompleta:{campo}")
    with _TRAVA_CACHE:
        _CACHE_DESCOBERTA[issuer] = (time.monotonic() + DESCOBERTA_TTL_S, doc)
    return doc


def _buscar_jwks(jwks_uri: str) -> KeySet:
    try:
        r = httpx.get(jwks_uri, timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        return KeySet.import_key_set(r.json())
    except httpx.HTTPError as e:
        raise ErroOidc(f"jwks_indisponivel:{type(e).__name__}:{e}") from e


def jwks_de(jwks_uri: str, *, forcar: bool = False) -> KeySet:
    with _TRAVA_CACHE:
        cache = _CACHE_JWKS.get(jwks_uri)
    if not forcar and cache is not None and cache[0] > time.monotonic():
        return cache[1]
    ks = _buscar_jwks(jwks_uri)
    with _TRAVA_CACHE:
        _CACHE_JWKS[jwks_uri] = (time.monotonic() + JWKS_TTL_S, ks)
    return ks


def _cabecalho_de(id_token: str) -> dict:
    try:
        parte = id_token.split(".", 2)[0]
        parte += "=" * (-len(parte) % 4)
        return json.loads(base64.urlsafe_b64decode(parte))
    except Exception as e:  # noqa: BLE001 — token corrompido, nunca 500
        raise ErroOidc(f"cabecalho_ilegivel:{e}") from e


def validar_id_token(
    id_token: str, *, jwks_uri: str, issuer: str, client_id: str, nonce_esperado: str
) -> dict[str, Any]:
    """Valida assinatura (JWKS com refetch em cima de kid desconhecido = rotação) e depois, À PARTE, as
    claims (issuer, audience, exp/iat com folga, nonce) — as 4 cláusulas literais do portão do item, cada
    uma com o seu próprio `ErroOidc` para o log dizer qual falhou (nunca a resposta HTTP)."""
    cabecalho = _cabecalho_de(id_token)
    alg = cabecalho.get("alg")
    if alg not in ALGORITMOS_ACEITOS:
        raise ErroOidc(f"algoritmo_recusado:{alg!r}")
    ks = jwks_de(jwks_uri)
    try:
        token = joserfc_jwt.decode(id_token, ks, algorithms=list(ALGORITMOS_ACEITOS))
    except JoseError as e:
        if "kid" in str(e).lower() or type(e).__name__ == "InvalidKeyIdError":
            ks = jwks_de(jwks_uri, forcar=True)  # chave pode ter rotacionado no IdP; uma tentativa nova só
            try:
                token = joserfc_jwt.decode(id_token, ks, algorithms=list(ALGORITMOS_ACEITOS))
            except JoseError as e2:
                raise ErroOidc(f"assinatura_invalida:{type(e2).__name__}:{e2}") from e2
        else:
            raise ErroOidc(f"assinatura_invalida:{type(e).__name__}:{e}") from e
    registro = joserfc_jwt.JWTClaimsRegistry(
        now=int(time.time()),
        leeway=FOLGA_RELOGIO_S,
        iss={"essential": True, "value": issuer},
        aud={"essential": True, "value": client_id},
        exp={"essential": True},
        iat={"essential": True},
        nonce={"essential": True, "value": nonce_esperado},
        sub={"essential": True},
    )
    try:
        registro.validate(token.claims)
    except JoseError as e:
        raise ErroOidc(f"claim_invalida:{type(e).__name__}:{e}") from e
    return token.claims


# ---------------------------------------------------------------- PKCE (RFC 7636), state e nonce
def gerar_par_pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)[:128]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verificador, desafio


# ================================================================== login federado (GET /api/sso/oidc/*)
def _redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/api/sso/oidc/retorno"


def _tenant_publico(slug: str) -> dict:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.tenant_publico(%s)", (slug,))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
    return r


def provedores_de(slug: str) -> list[dict]:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedores_oidc_de(%s)", (slug,))
        return list(cur.fetchall())


@router.get("/sso/oidc/iniciar", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def sso_oidc_iniciar(inquilino: str, request: Request, provedor_id: int | None = None):
    slug = inquilino.strip().lower()
    t = _tenant_publico(slug)
    if not t["ativo"]:
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    provedores = provedores_de(slug)
    if not provedores:
        raise ErroAPI(404, "oidc_sem_configuracao", "este inquilino não tem login OIDC habilitado")
    provedor = next((p for p in provedores if p["provedor_id"] == provedor_id), None) if provedor_id else provedores[0]
    if provedor is None:
        raise ErroAPI(404, "oidc_provedor_inexistente", "provedor OIDC inexistente ou desabilitado neste inquilino")
    try:
        doc = descoberta(provedor["issuer"])
    except ErroOidc as e:
        log.warning(
            "descoberta OIDC falhou (inquilino=%s provedor=%s): %s", slug, provedor["provedor_id"], e.motivo_interno
        )
        raise ErroAPI(503, "oidc_indisponivel", "provedor de login indisponível; tente o login local") from e
    verificador, desafio = gerar_par_pkce()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = _redirect_uri(request)
    with db.db() as cur:
        cur.execute(
            "SELECT plat.oidc_transacao_abrir(%s, %s, %s, %s, %s, %s)",
            (provedor["provedor_id"], provedor["tenant_id"], state, nonce, verificador, redirect_uri),
        )
    params = {
        "response_type": "code",
        "client_id": provedor["client_id"],
        "redirect_uri": redirect_uri,
        "scope": provedor["escopos"],
        "state": state,
        "nonce": nonce,
        "code_challenge": desafio,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(doc["authorization_endpoint"] + "?" + urlencode(params), status_code=302)


def _falha_retorno(request: Request, motivo_interno: str, motivo_publico: str = "token_invalido") -> ErroAPI:
    log.warning("login OIDC recusado: %s", motivo_interno)  # o motivo específico NUNCA vai para a resposta
    request.state.resultado = "oidc_recusado"
    return ErroAPI(401, motivo_publico, "não foi possível concluir o login pela organização")


@router.get("/sso/oidc/retorno", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def sso_oidc_retorno(
    request: Request, resposta: Response, code: str | None = None, state: str | None = None, error: str | None = None
):
    if error:
        raise _falha_retorno(request, f"idp_recusou:{error}")
    if not code or not state:
        raise _falha_retorno(request, "code_ou_state_ausente")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.oidc_transacao_consumir(%s)", (state,))
        transacao = cur.fetchone()
    if transacao is None:
        # state desconhecido, já usado (replay) ou expirado -- as 3 causas são indistinguíveis de propósito
        raise _falha_retorno(request, f"state_invalido_ou_reusado:{state[:8]}...")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_oidc_por_id(%s)", (transacao["provedor_id"],))
        provedor = cur.fetchone()
    if provedor is None or not provedor["habilitado"]:
        raise _falha_retorno(request, "provedor_desabilitado_apos_iniciar")
    if not provedor["tenant_ativo"]:
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    try:
        doc = descoberta(provedor["issuer"])
    except ErroOidc as e:
        raise _falha_retorno(request, f"descoberta_falhou:{e.motivo_interno}", "oidc_indisponivel") from e
    corpo_token = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": transacao["redirect_uri"],
        "client_id": provedor["client_id"],
        "code_verifier": transacao["code_verifier"],
    }
    if provedor["client_secret_cifrada"]:
        try:
            corpo_token["client_secret"] = decifrar_client_secret(
                provedor["client_secret_cifrada"], settings.PLAT_SECRET
            )
        except ValueError:
            log.error("client_secret do provedor OIDC %s ilegível (PLAT_SECRET trocado?)", provedor["provedor_id"])
            raise ErroAPI(503, "oidc_indisponivel", "provedor de login indisponível; tente o login local") from None
    try:
        r = httpx.post(doc["token_endpoint"], data=corpo_token, timeout=HTTP_TIMEOUT_S)
    except httpx.HTTPError as e:
        raise _falha_retorno(request, f"token_endpoint_indisponivel:{e}", "oidc_indisponivel") from e
    if r.status_code != 200:
        # code reusado (replay direto no token_endpoint, sem passar pela nossa transação de novo -- ela já foi
        # consumida acima e não devolveria segunda vez) ou code inválido: o IdP recusa, nunca cria sessão
        raise _falha_retorno(request, f"token_endpoint_recusou:{r.status_code}:{r.text[:200]}")
    tokens = r.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise _falha_retorno(request, "resposta_sem_id_token")
    try:
        claims = validar_id_token(
            id_token,
            jwks_uri=doc["jwks_uri"],
            issuer=provedor["issuer"],
            client_id=provedor["client_id"],
            nonce_esperado=transacao["nonce"],
        )
    except ErroOidc as e:
        raise _falha_retorno(request, e.motivo_interno) from e
    sub = claims["sub"]
    email = claims.get("email")
    nome = claims.get("name") or (email.split("@")[0] if email else sub)
    login = (email.split("@")[0] if email else sub).strip().lower().replace(" ", ".")[:120] or sub[:120]
    sujeito_externo = f"{provedor['issuer']}#{sub}"
    tenant_slug = provedor["tenant_slug"]
    valores_grupos = claims.get(provedor["atributo_grupos"])
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_oidc_modelo(%s)", (provedor["provedor_id"],))
        modelo = cur.fetchone() or {"modelo": "generico", "api_base": None}
    if modelo["modelo"] == "govbr":
        # item L0-08-c: `sub` é o CPF — nunca em claro no login, no sujeito externo, no evento ou no log;
        # nível/selos/amr viram valores do mapeamento (regras do L0-08-e), junto com o atributo de grupos se houver
        pseud = govbr.pseudonimo(sub)
        sujeito_externo = f"{provedor['issuer']}#{pseud}"
        login = govbr.login_de(claims, pseud)
        nome = claims.get("name") or login
        extra = claims.get(provedor["atributo_grupos"]) or []
        valores_grupos = govbr.valores_de(claims, tokens.get("access_token"), modelo["api_base"]) + (
            [extra] if isinstance(extra, str) else list(extra)
        )
    # item L0-08-e: regras de provisionamento do provedor (criação, padrões, mapa valor->papel/grupos, atualizar,
    # desligar) decidem e provisionam; 403 sem_grupo_mapeado/convite_necessario/conta_desligada saem de lá
    try:
        resultado = provisionamento.aplicar(
            request, "oidc", provedor["provedor_id"], provedor["tenant_id"], tenant_slug, login, nome, email,
            valores_grupos, sujeito_externo, provedor["mapa_grupo_perfil"],
            provedor["perfil_padrao"],
        )
    except psycopg2.errors.RaiseException as e:
        if (e.diag.message_primary or "").strip() == "login_em_uso_local":
            raise _falha_retorno(request, "login_em_uso_local", "login_em_uso_local") from e
        raise erro_do_banco(e) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    linha = resultado["linha"]
    perfil = resultado["perfil"]
    ctx = db.Contexto(linha["tenant_id"], linha["usuario_id"], login)
    with db.db(ctx) as cur:
        registrar_evento(
            cur,
            request,
            "usuarios/criar" if resultado["criado"] else "usuarios/atualizar",
            "usuario",
            linha["usuario_id"],
            {"origem": "oidc", "perfil": perfil, "perfil_anterior": resultado["perfil_anterior"]},
        )
        provisionamento.registrar_efeitos(cur, request, resultado, "oidc", linha["usuario_id"])
    politica_sessao = politica_de(linha["config"], tenant_slug)
    saida = _abrir_sessao(request, resposta, ctx, linha["usuario_id"], politica_sessao, "oidc", None)
    saida["end_session_endpoint"] = doc.get("end_session_endpoint")
    return saida


@router.get(
    "/sso/oidc/logout",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S", "x-privilegio": "proprio"},
)
def sso_oidc_logout(request: Request):
    """Encerra a sessão local sempre (mesmo passo de app.auth.rotas_login.logout); quando a conta é OIDC e o
    provedor associado publica `end_session_endpoint`, devolve a URL no cabeçalho `X-Oidc-End-Session` para o
    front completar a propagação no IdP (RP-Initiated Logout não tem como o backend, sozinho, encerrar a
    sessão do NAVEGADOR no IdP — só redirecionando o navegador para lá)."""
    cookie = request.cookies.get(COOKIE)
    resposta = Response(status_code=204)
    end_session = None
    if cookie:
        auth = None
        try:
            auth = resolver(request)
        except ErroAPI:
            auth = None
        if auth is not None:
            with db.db(auth.contexto()) as cur:
                cur.execute("SELECT origem, sujeito_externo FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
                u = cur.fetchone()
                if u and u["origem"] == "oidc" and u["sujeito_externo"] and "#" in u["sujeito_externo"]:
                    issuer = u["sujeito_externo"].rsplit("#", 1)[0]
                    try:
                        end_session = descoberta(issuer).get("end_session_endpoint")
                    except ErroOidc:
                        end_session = None
                registrar_evento(cur, request, "usuarios/sair", "usuario", auth.usuario_id)
                cur.execute("SELECT plat.auth_sessao_encerrar(%s)", (auth.sessao_hash,))
        else:
            with db.db() as cur:
                cur.execute("SELECT plat.auth_sessao_encerrar(%s)", (sha256_hex(cookie),))
    request.state.resultado = "logout"
    apagar_cookie(resposta, request)
    if end_session:
        resposta.headers["X-Oidc-End-Session"] = end_session
    return resposta


# ================================================================== configuração do provedor por inquilino
# (GET/PUT/DELETE /api/org/oidc; privilégio org.integracoes — o mesmo do LDAP/SMTP/webhooks/CORS, ADR 0002
# seção 13). Nunca devolve o client_secret cifrado nem em claro; PUT aceita `client_secret` em claro só para
# cifrar e gravar (nunca ecoado de volta) e, se omitido numa atualização, preserva o segredo anterior.
class ProvedorOidcEntrada(Modelo):
    habilitado: bool = True
    rotulo: str = Field(default="Entrar com a organização", min_length=1, max_length=120)
    ordem: int = 0
    issuer: str = Field(min_length=8, max_length=250)
    client_id: str = Field(min_length=1, max_length=250)
    client_secret: str | None = Field(default=None, max_length=500)
    escopos: str = Field(default="openid profile email", min_length=5, max_length=250)
    atributo_grupos: str = Field(default="groups", min_length=1, max_length=64)
    perfil_padrao: str | None = None
    mapa_grupo_perfil: dict[str, str] = Field(default_factory=dict)
    # item L0-08-c: 'govbr' liga o adaptador do Login Único (nível/selos/amr como valores do mapeamento; CPF
    # pseudonimizado); api_base = API de confiabilidades (padrão pela issuer: produção ou staging)
    modelo: str = Field(default="generico", pattern="^(generico|govbr)$")
    api_base: str | None = Field(default=None, max_length=250)


class ProvedorOidcSaida(Saida):
    id: int
    habilitado: bool
    rotulo: str
    ordem: int
    issuer: str
    client_id: str
    tem_client_secret: bool
    escopos: str
    atributo_grupos: str
    perfil_padrao: str | None
    mapa_grupo_perfil: dict[str, Any]
    modelo: str
    api_base: str | None


def _api_base_de(corpo: "ProvedorOidcEntrada") -> str | None:
    """gov.br: API de confiabilidades explícita, ou deduzida do issuer (staging/produção); genérico: nada."""
    if corpo.modelo != "govbr":
        return None
    if corpo.api_base:
        if not _url_valida_https_ou_teste(corpo.api_base):
            raise ErroAPI(422, "validacao", "api_base precisa ser https:// (http:// só em loopback fora de produção)",
                          {"campo": "api_base"})
        return corpo.api_base.rstrip("/")
    if corpo.issuer.rstrip("/") == govbr.ISSUER_STAGING:
        return govbr.API_STAGING
    if corpo.issuer.rstrip("/") == govbr.ISSUER_PRODUCAO:
        return govbr.API_PRODUCAO
    return None


def _validar_entrada(corpo: ProvedorOidcEntrada) -> None:
    if not _url_valida_https_ou_teste(corpo.issuer):
        raise ErroAPI(
            422,
            "validacao",
            "issuer precisa ser https:// (http:// só é aceito em loopback fora de produção)",
            {"campo": "issuer"},
        )
    if corpo.perfil_padrao is not None and corpo.perfil_padrao not in PERFIS_VALIDOS:
        raise ErroAPI(422, "validacao", f"perfil_padrao precisa ser um de {PERFIS_VALIDOS}", {"campo": "perfil_padrao"})
    for grupo, perfil in corpo.mapa_grupo_perfil.items():
        if perfil not in PERFIS_VALIDOS:
            raise ErroAPI(
                422,
                "validacao",
                f"mapa_grupo_perfil[{grupo!r}] precisa ser um de {PERFIS_VALIDOS}",
                {"campo": "mapa_grupo_perfil", "grupo": grupo},
            )


def _saida_de(r: dict) -> dict:
    return {
        "id": r["id"],
        "habilitado": r["habilitado"],
        "rotulo": r["rotulo"],
        "ordem": r["ordem"],
        "issuer": r["issuer"],
        "client_id": r["client_id"],
        "tem_client_secret": bool(r["client_secret_cifrada"]),
        "escopos": r["escopos"],
        "atributo_grupos": r["atributo_grupos"],
        "perfil_padrao": r["perfil_padrao"],
        "mapa_grupo_perfil": r["mapa_grupo_perfil"] or {},
        "modelo": r.get("modelo") or "generico",
        "api_base": r.get("api_base"),
    }


@router.get(
    "/org/oidc",
    response_model=list[ProvedorOidcSaida],
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_oidc_listar(auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.provedor_oidc WHERE tenant_id = plat.tenant_atual() ORDER BY ordem, id")
        return [_saida_de(r) for r in cur.fetchall()]


@router.post(
    "/org/oidc",
    status_code=201,
    response_model=ProvedorOidcSaida,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_oidc_criar(corpo: ProvedorOidcEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    _validar_entrada(corpo)
    # client público (sem client_secret, PKCE puro) é uma escolha válida; nada a recusar aqui
    client_secret_cifrada = (
        cifrar_client_secret(corpo.client_secret, settings.PLAT_SECRET) if corpo.client_secret else None
    )
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                INSERT INTO plat.provedor_oidc(tenant_id, habilitado, rotulo, ordem, issuer, client_id,
                    client_secret_cifrada, escopos, atributo_grupos, perfil_padrao, mapa_grupo_perfil,
                    criado_por, atualizado_por, modelo, api_base)
                VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    corpo.habilitado,
                    corpo.rotulo,
                    corpo.ordem,
                    corpo.issuer,
                    corpo.client_id,
                    client_secret_cifrada,
                    corpo.escopos,
                    corpo.atributo_grupos,
                    corpo.perfil_padrao,
                    json.dumps(corpo.mapa_grupo_perfil),
                    auth.usuario_id,
                    auth.usuario_id,
                    corpo.modelo,
                    _api_base_de(corpo),
                ),
            )
            r = cur.fetchone()
            registrar_evento(
                cur,
                request,
                "org/oidc_configurar",
                "provedor_oidc",
                r["id"],
                {"issuer": corpo.issuer, "rotulo": corpo.rotulo},
            )
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(
            409, "provedor_duplicado", "já existe um provedor com este issuer e client_id neste inquilino"
        ) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _saida_de(r)


@router.put(
    "/org/oidc/{provedor_id}",
    response_model=ProvedorOidcSaida,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_oidc_atualizar(
    provedor_id: int, corpo: ProvedorOidcEntrada, request: Request, auth: Auth = autenticado("org.integracoes")
):
    _validar_entrada(corpo)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, client_secret_cifrada FROM plat.provedor_oidc "
            "WHERE id = %s AND tenant_id = plat.tenant_atual()",
            (provedor_id,),
        )
        anterior = cur.fetchone()
    if anterior is None:
        raise ErroAPI(404, "provedor_inexistente", "provedor OIDC inexistente neste inquilino")
    client_secret_cifrada = (
        cifrar_client_secret(corpo.client_secret, settings.PLAT_SECRET)
        if corpo.client_secret
        else anterior["client_secret_cifrada"]
    )
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                UPDATE plat.provedor_oidc SET habilitado=%s, rotulo=%s, ordem=%s, issuer=%s, client_id=%s,
                    client_secret_cifrada=%s, escopos=%s, atributo_grupos=%s, perfil_padrao=%s,
                    mapa_grupo_perfil=%s::jsonb, atualizado_por=%s, atualizado_em=now(), modelo=%s, api_base=%s
                WHERE id = %s AND tenant_id = plat.tenant_atual()
                RETURNING *
                """,
                (
                    corpo.habilitado,
                    corpo.rotulo,
                    corpo.ordem,
                    corpo.issuer,
                    corpo.client_id,
                    client_secret_cifrada,
                    corpo.escopos,
                    corpo.atributo_grupos,
                    corpo.perfil_padrao,
                    json.dumps(corpo.mapa_grupo_perfil),
                    auth.usuario_id,
                    corpo.modelo,
                    _api_base_de(corpo),
                    provedor_id,
                ),
            )
            r = cur.fetchone()
            registrar_evento(
                cur,
                request,
                "org/oidc_configurar",
                "provedor_oidc",
                r["id"],
                {"issuer": corpo.issuer, "rotulo": corpo.rotulo},
            )
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(
            409, "provedor_duplicado", "já existe um provedor com este issuer e client_id neste inquilino"
        ) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _saida_de(r)


@router.delete(
    "/org/oidc/{provedor_id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_oidc_remover(provedor_id: int, request: Request, auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "DELETE FROM plat.provedor_oidc WHERE id = %s AND tenant_id = plat.tenant_atual() RETURNING id",
            (provedor_id,),
        )
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "provedor_inexistente", "provedor OIDC inexistente neste inquilino")
        registrar_evento(cur, request, "org/oidc_remover", "provedor_oidc", provedor_id, {})
    return Response(status_code=204)
