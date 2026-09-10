"""Login federado OIDC e SAML 2.0 por inquilino (item L0-08-sso, pai do L0-08-d-ldap; ADR 0002 seção 13
"Gancho para SSO"; docs/adr/20260906T2122-sso-oidc-saml.md tem o raciocínio completo). Módulo isolado no
mesmo padrão de app/auth/ldap.py: valida a identidade no provedor externo e REAPROVEITA `_abrir_sessao`
(app/auth/rotas_login.py) a partir daí — cookie, evento `usuarios/entrar` e política de sessão são os do
login local, nunca um segundo caminho.

OIDC (Authorization Code + PKCE S256, conforme com Keycloak/Authentik/gov.br — o gov.br É um provedor OIDC,
não um terceiro protocolo):
  GET /api/login/oidc/iniciar?inquilino=<slug>  → 302 para o authorization_endpoint do IdP (state, nonce e
      verificador PKCE em plat.sso_transacao, validade curta, consumo atômico anti-replay);
  GET /api/login/oidc/retorno?code&state        → troca o código no token_endpoint, valida o id_token
      (assinatura RS256 via jwks_uri da descoberta, issuer, audience, exp/iat com folga, nonce), mapeia
      grupos→perfil, provisiona (plat.sso_provisionar) e abre sessão → 303 para '/' com o cookie.

SAML 2.0 (Web Browser SSO Profile, AuthnRequest por HTTP-Redirect, resposta por HTTP-POST):
  GET /api/login/saml/iniciar?inquilino=<slug>  → 302 para o IdP com SAMLRequest (DEFLATE+base64) e
      RelayState (= estado da transação; o ID do AuthnRequest fica guardado para conferir InResponseTo);
  POST /api/login/saml/acs                      → valida a resposta e abre sessão → 303 para '/';
  GET /api/login/saml/metadata?inquilino=<slug> → EntityDescriptor do SP deste inquilino (para cadastrar
      no IdP; WantAssertionsSigned="true" — a assertion SEM assinatura é recusada, sempre).

Validação da assinatura SAML é PRÓPRIA (lxml + cryptography, sem signxml: instalá-lo trocaria as versões
de lxml/cryptography do ambiente, o que o laço proíbe). Regras duras, na ordem em que são aplicadas:
  1. XML parseado com resolve_entities=False e no_network=True (XXE nunca resolve);
  2. raiz samlp:Response com EXATAMENTE uma saml:Assertion (duas assertions = tentativa de wrapping, XSW);
  3. a Assertion tem de ter filho ds:Signature (assertion sem assinatura = 401 — a refutação do item);
  4. a Reference da assinatura aponta para o ID DESTA assertion; transforms ⊆ {enveloped, exc-c14n};
     DigestMethod ∈ {sha256, sha384, sha512} (sha1 nunca); SignatureMethod = rsa-sha256/384/512;
  5. o resumo é recomputado sobre a assertion canonicalizada (exc-c14n) SEM o elemento Signature e tem de
     bater com DigestValue; a assinatura é verificada sobre o SignedInfo canonicalizado com a chave pública
     do certificado CONFIGURADO no inquilino — KeyInfo/X509Certificate embutido no XML é ignorado por
     inteiro (confiar nele seria deixar o atacante escolher a chave);
  6. condições (NotBefore/NotOnOrAfter com folga de relógio), AudienceRestriction = entityID deste SP,
     SubjectConfirmation bearer (Recipient = URL do ACS, NotOnOrAfter, InResponseTo = pedido guardado).
Só DEPOIS das 6 etapas os atributos são lidos — e lidos da assertion validada, nunca do documento inteiro.

O login local NUNCA depende deste módulo: provedor fora do ar, mal configurado ou desligado devolve
503/401 só nas rotas /api/login/{oidc,saml}/*; /api/login (local) segue respondendo (portão do item)."""

import base64
import datetime
import hashlib
import json
import logging
import secrets
import time
import zlib
from typing import Any
from urllib.parse import unquote_plus, urlencode, urlsplit
from xml.sax.saxutils import escape as escapar_xml

import httpx
import jwt
import psycopg2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256, SHA384, SHA512
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from lxml import etree
from pydantic import Field

from app import db, limites
from app.auth.comum import erro_do_banco, registrar_evento
from app.auth.modelos import Modelo, Saida
from app.auth.politica import politica_de
from app.auth.privilegios import ORDEM_PERFIL
from app.auth.rotas_login import _abrir_sessao  # mesma criação de sessão do login local/LDAP; ver docstring
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.auth.sso")
router = APIRouter(prefix="/api", tags=["login"])
PREFIXO_CIFRA = "encsso:v1:"
PERFIS_VALIDOS = ("admin", "editor", "visualizador", "campo")
TIPOS = ("oidc", "saml")

NS_SAMLP = "urn:oasis:names:tc:SAML:2.0:protocol"
NS_SAML = "urn:oasis:names:tc:SAML:2.0:assertion"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_C14N_EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"
ALG_C14N = {NS_C14N_EXC, NS_C14N_EXC + "WithComments"}
ALG_ENVOLVIDA = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
ALG_RESUMO = {
    "http://www.w3.org/2001/04/xmlenc#sha256": "SHA256",
    "http://www.w3.org/2001/04/xmldsig-more#sha384": "SHA384",
    "http://www.w3.org/2001/04/xmlenc#sha512": "SHA512",
}
ALG_ASSINATURA = {
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": SHA256,
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384": SHA384,
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512": SHA512,
}
ATRIBUTOS_NOME = (
    "nome", "name", "displayName", "cn", "givenName",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
)
ATRIBUTOS_EMAIL = (
    "email", "mail", "emailAddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
)


class ErroSSO(Exception):
    """Falha de validação/indisponibilidade do provedor federado. `motivo_interno` vai SÓ ao log; o corpo
    devolvido ao navegador é sempre o genérico (nunca distingue 'token expirado' de 'assinatura errada')."""

    def __init__(self, motivo_interno: str, indisponivel: bool = False):
        self.motivo_interno = motivo_interno
        self.indisponivel = indisponivel
        super().__init__(motivo_interno)


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _instante(texto: str) -> datetime.datetime:
    """Instante SAML/OIDC ('2026-09-06T21:00:00Z' ou com fração/offset). Levanta ErroSSO se inválido."""
    try:
        bruto = texto.strip()
        if bruto.endswith("Z"):
            bruto = bruto[:-1] + "+00:00"
        t = datetime.datetime.fromisoformat(bruto)
        if t.tzinfo is None:
            raise ValueError("sem fuso")
        return t.astimezone(datetime.UTC)
    except (ValueError, AttributeError) as e:
        raise ErroSSO(f"instante_invalido:{texto!r}") from e


# ---------------------------------------------------------------- cifra do segredo de cliente OIDC (mesmo
# esquema AES-GCM do segredo TOTP/da senha de bind LDAP, com prefixo e AAD próprios para nunca haver reuso
# cruzado de material entre os três usos). O segredo do USUÁRIO não existe neste fluxo (é o id_token, nunca
# gravado); o que se guarda é só o segredo de cliente que o IdP exige de cliente confidencial.
def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"sso-cliente").digest()


def cifrar_segredo(segredo: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, segredo.encode("utf-8"), b"plat-sso-cliente")
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar_segredo(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("segredo de cliente sem o prefixo encsso:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], b"plat-sso-cliente").decode("utf-8")


# ---------------------------------------------------------------- endereços: todo endpoint de IdP (emissor
# OIDC, endpoints descobertos, URL de SSO SAML) tem de ser https — exceto laço de máquina local, para a
# suíte de teste desta máquina (mock OIDC em 127.0.0.1) e para IdP de laboratório do operador. Quem configura
# é o admin do inquilino (privilégio org.integracoes), mas a regra vale para a configuração também, não só
# para a chamada.
def _url_externa_ok(url: str) -> bool:
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    if partes.scheme == "https" and partes.hostname:
        return True
    return partes.scheme == "http" and partes.hostname in ("127.0.0.1", "localhost", "::1")


# ---------------------------------------------------------------- mapeamento de grupo -> perfil (mesmo
# vocabulário fechado de 4 perfis da D5 do L0_CONCEITO, já usado pelo LDAP). Aqui os valores são nomes
# simples (claim OIDC / atributo SAML), não DNs: casa exata, sem distinção de caixa. Empate → perfil de
# MAIOR alcance (ORDEM_PERFIL de app/auth/privilegios.py).
def perfil_por_grupos(valores_grupo: list[str], mapa: dict[str, Any], perfil_padrao: str | None) -> str | None:
    normalizado = {str(k).strip().lower(): v for k, v in (mapa or {}).items()}
    candidatos = [
        normalizado[str(valor).strip().lower()]
        for valor in valores_grupo
        if str(valor).strip().lower() in normalizado
    ]
    candidatos = [c for c in candidatos if c in ORDEM_PERFIL]
    if not candidatos:
        return perfil_padrao if perfil_padrao in ORDEM_PERFIL else None
    return max(candidatos, key=lambda p: ORDEM_PERFIL[p])


def _login_de_bruto(valor: str) -> str:
    """O login local precisa casar o padrão de plat.usuario (^[a-z0-9][a-z0-9._@-]*$). O claim/NameID do IdP
    vem em caixa e caracteres livres: normaliza (minúsculas, tudo fora do vocabulário vira '.') e só aceita
    se o resultado continuar casando o padrão — senão recusa com motivo claro no log (o administrador ajusta
    claim_login/atributo de login), nunca inventa um login irreconhecível para o usuário."""
    bruto = "".join(c if c in "abcdefghijklmnopqrstuvwxyz0123456789._@-" else "." for c in valor.strip().lower())
    bruto = bruto.strip(".")[:128]
    if not bruto or not bruto[0].isalnum():
        raise ErroSSO(f"login_federado_invalido:{valor!r}")
    return bruto


def _valores_texto(valor: Any) -> list[str]:
    """Claim de grupos pode vir lista ou string única (Keycloak manda lista; alguns IdPs, string)."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor]
    return [str(valor)]


# ---------------------------------------------------------------- banco: provedor (pré-contexto), transação
# (criação/consumo atômico) e provisionamento (upsert que nunca cruza origem)
def _provedor_de(tenant_slug: str, tipo: str) -> dict:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_sso_de(%s, %s)", (tenant_slug, tipo))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
    return r


def _provedor_habilitado(r: dict, tipo: str, request: Request) -> None:
    """503 de inquilino suspenso / 403 de provedor desligado, idênticos em forma aos do login local/LDAP."""
    if not r["tenant_ativo"]:
        request.state.resultado = "suspenso"
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    if not r["habilitado"]:
        request.state.resultado = "externo_desabilitado"
        raise ErroAPI(403, "login_sso_desabilitado", f"este inquilino não tem login por {tipo.upper()} habilitado")


def _transacao_criar(tenant_id: int, tipo: str, estado: str, nonce: str | None, verificador: str | None,
                     pedido_id: str | None) -> None:
    with db.db() as cur:
        cur.execute(
            "SELECT plat.sso_transacao_criar(%s, %s, %s, %s, %s, %s, %s)",
            (tenant_id, tipo, estado, nonce, verificador, pedido_id, limites.SSO_TRANSACAO_MINUTOS),
        )


def _transacao_consumir(estado: str, tipo: str) -> dict:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.sso_transacao_consumir(%s, %s)", (estado, tipo))
        r = cur.fetchone()
    if r is None:
        # state desconhecido, já consumido (replay) ou vencido: tudo a mesma recusa genérica
        raise ErroSSO("estado_desconhecido_ou_vencido")
    return r


def _provisionar_e_abrir(request: Request, r: dict, tipo: str, *, sujeito: str,
                         login: str, nome: str, email: str | None, grupos: list[str]):
    """Caminho comum do fim dos dois protocolos: perfil pelos grupos → upsert (nunca cruza origem) →
    auth_login (mesma função do login local, agora com contexto) → _abrir_sessao reaproveitado."""
    tenant_slug = r["tenant_slug"]
    perfil = perfil_por_grupos(grupos, r["mapa_grupo_perfil"] or {}, r["perfil_padrao"])
    if perfil is None:
        request.state.resultado = "sem_grupo_mapeado"
        raise ErroAPI(
            403,
            "sem_grupo_mapeado",
            "nenhum grupo do provedor está mapeado para um perfil desta plataforma; fale com o administrador",
        )
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT * FROM plat.sso_provisionar(%s, %s, %s, %s, %s, %s, %s, true)",
                (r["tenant_id"], tipo, login, nome, email, perfil, sujeito),
            )
            prov = cur.fetchone()
            cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (tenant_slug, login))
            linha = cur.fetchone()
    except psycopg2.errors.RaiseException as e:
        if (e.diag.message_primary or "").strip() == "login_em_uso_outra_origem":
            request.state.resultado = "login_em_uso_outra_origem"
            raise ErroAPI(
                409,
                "login_em_uso_outra_origem",
                "já existe uma conta com este login criada por outra origem; fale com o administrador",
            ) from e
        raise erro_do_banco(e) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    ctx = db.Contexto(linha["tenant_id"], linha["usuario_id"], login)
    with db.db(ctx) as cur:
        registrar_evento(
            cur,
            request,
            "usuarios/criar" if prov["criado"] else "usuarios/atualizar",
            "usuario",
            linha["usuario_id"],
            {"origem": tipo, "perfil": perfil, "perfil_anterior": prov["perfil_anterior"]},
        )
    politica_sessao = politica_de(linha["config"], tenant_slug)
    redirecionar = RedirectResponse(url="/", status_code=303)
    _abrir_sessao(request, redirecionar, ctx, linha["usuario_id"], politica_sessao, tipo, None)
    return redirecionar


def _falha_federada(request: Request, e: ErroSSO, tenant_slug: str, tipo: str) -> ErroAPI:
    """Tradução única dos dois protocolos: indisponibilidade do IdP = 503 (nunca derruba o login local,
    que é outra rota); qualquer falha de validação = 401 genérico (o motivo fica só no log)."""
    if e.indisponivel:
        log.warning("provedor %s do inquilino %s indisponível: %s", tipo, tenant_slug, e.motivo_interno)
        request.state.resultado = "provedor_indisponivel"
        return ErroAPI(503, "sso_indisponivel", "provedor de login indisponível; tente o login local")
    log.warning("login %s do inquilino %s recusado: %s", tipo, tenant_slug, e.motivo_interno)
    request.state.resultado = "federacao_invalida"
    return ErroAPI(401, "federacao_invalida", "não foi possível confirmar sua identidade no provedor")


def _base(request: Request) -> str:
    """Endereço público desta instância visto pelo navegador (redirect_uri do OIDC, entityID/ACS do SAML).
    Vem da própria requisição: a instância é mono-domínio e o nginx preserva o Host — nunca um endereço
    gravado em configuração que poderia divergir do real."""
    return str(request.base_url)


# ================================================================== OIDC
_DESCOBERTA: dict[str, tuple[float, dict]] = {}  # emissor -> (validade_monotonic, documento)


def _descobrir(emissor: str) -> dict:
    """Documento de descoberta (<emissor>/.well-known/openid-configuration), com cache em memória de
    SSO_DESCOBERTA_CACHE_S. Emissor sem documento conforme (sem os 3 endpoints ou com issuer divergente)
    é erro de configuração/indisponibilidade, nunca segue adiante com endereço inventado."""
    agora = time.monotonic()
    em_cache = _DESCOBERTA.get(emissor)
    if em_cache and em_cache[0] > agora:
        return em_cache[1]
    base = emissor.rstrip("/")
    url = f"{base}/.well-known/openid-configuration"
    try:
        resposta = httpx.get(url, timeout=limites.SSO_TIMEOUT_S, follow_redirects=True)
        resposta.raise_for_status()
        doc = resposta.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ErroSSO(f"descoberta_falhou:{type(e).__name__}", indisponivel=True) from e
    issuer_doc = str(doc.get("issuer") or "").rstrip("/")
    if issuer_doc != base:
        raise ErroSSO(f"issuer_divergente:{issuer_doc!r}")
    endpoints = {k: doc.get(k) for k in ("authorization_endpoint", "token_endpoint", "jwks_uri")}
    if not all(isinstance(v, str) and _url_externa_ok(v) for v in endpoints.values()):
        raise ErroSSO("descoberta_incompleta_ou_insegura")
    _DESCOBERTA[emissor] = (agora + limites.SSO_DESCOBERTA_CACHE_S, doc)
    return doc


def _cliente_jwks(jwks_uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=limites.SSO_DESCOBERTA_CACHE_S,
                           timeout=limites.SSO_TIMEOUT_S)


def validar_id_token(id_token: str, *, emissor: str, cliente_id: str, nonce: str,
                     cliente_jwks: jwt.PyJWKClient) -> dict:
    """Valida o id_token devolvido na troca de código: assinatura RS256 pela chave do JWKS do PRÓPRIO
    emissor, issuer/audience exatos, exp/iat com a folga de relógio do módulo (token expirado = 401 — a
    refutação do item) e nonce igual ao da transação (resposta colada de outro login não entra)."""
    try:
        chave = cliente_jwks.get_signing_key_from_jwt(id_token).key
    except jwt.PyJWKClientError as e:
        raise ErroSSO(f"jwks_falhou:{type(e).__name__}", indisponivel=True) from e
    try:
        claims = jwt.decode(
            id_token,
            key=chave,
            algorithms=["RS256"],
            audience=cliente_id,
            issuer=emissor,
            leeway=limites.SSO_DESVIO_RELOGIO_S,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise ErroSSO(f"id_token_invalido:{type(e).__name__}") from e
    if claims.get("nonce") != nonce:
        raise ErroSSO("nonce_divergente")
    return claims


@router.get("/login/oidc/iniciar", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def oidc_iniciar(inquilino: str, request: Request):
    tenant_slug = inquilino.strip().lower()
    r = _provedor_de(tenant_slug, "oidc")
    _provedor_habilitado(r, "oidc", request)
    if not _url_externa_ok(r["emissor"]):
        request.state.resultado = "sem_configuracao"
        raise ErroAPI(503, "sso_sem_configuracao", "login federado não está configurado neste inquilino")
    try:
        doc = _descobrir(r["emissor"])
    except ErroSSO as e:
        raise _falha_federada(request, e, tenant_slug, "oidc") from e
    estado = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    _transacao_criar(r["tenant_id"], "oidc", estado, nonce, verificador, None)
    parametros = {
        "response_type": "code",
        "client_id": r["cliente_id"],
        "redirect_uri": _base(request) + "api/login/oidc/retorno",
        "scope": "openid profile email",
        "state": estado,
        "nonce": nonce,
        "code_challenge": desafio,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(url=f"{doc['authorization_endpoint']}?{urlencode(parametros)}", status_code=302)


@router.get("/login/oidc/retorno", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def oidc_retorno(request: Request, code: str | None = None, state: str | None = None,
                 error: str | None = None):
    if error or not code or not state:
        # o IdP recusou (error=...) ou o callback veio incompleto: a mesma recusa genérica, sem vazar qual
        request.state.resultado = "federacao_invalida"
        raise ErroAPI(401, "federacao_invalida", "não foi possível confirmar sua identidade no provedor")
    try:
        transacao = _transacao_consumir(state.strip(), "oidc")
    except ErroSSO:
        request.state.resultado = "federacao_invalida"
        raise ErroAPI(401, "federacao_invalida", "não foi possível confirmar sua identidade no provedor") from None
    # o inquilino vem da TRANSAÇÃO, nunca de parâmetro do navegador: o callback não aceita inquilino solto
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_sso_de((SELECT slug FROM plat.tenant WHERE id = %s), 'oidc')",
                    (transacao["tenant_id"],))
        r = cur.fetchone()
    if r is None or not r["habilitado"]:
        request.state.resultado = "externo_desabilitado"
        raise ErroAPI(403, "login_sso_desabilitado", "este inquilino não tem login por OIDC habilitado")
    tenant_slug = r["tenant_slug"]
    try:
        doc = _descobrir(r["emissor"])
        campos = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _base(request) + "api/login/oidc/retorno",
            "client_id": r["cliente_id"],
            "code_verifier": transacao["verificador_pkce"],
        }
        if r["cliente_segredo_cifrado"]:
            try:
                campos["client_secret"] = decifrar_segredo(r["cliente_segredo_cifrado"], settings.PLAT_SECRET)
            except ValueError:
                raise ErroSSO("segredo_cliente_ilegivel", indisponivel=True) from None
        try:
            resposta = httpx.post(doc["token_endpoint"], data=campos, timeout=limites.SSO_TIMEOUT_S)
            resposta.raise_for_status()
            tokens = resposta.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ErroSSO(f"troca_codigo_falhou:{type(e).__name__}", indisponivel=True) from e
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise ErroSSO("resposta_sem_id_token")
        claims = validar_id_token(
            id_token, emissor=r["emissor"], cliente_id=r["cliente_id"], nonce=transacao["nonce"],
            cliente_jwks=_cliente_jwks(doc["jwks_uri"]),
        )
    except ErroSSO as e:
        raise _falha_federada(request, e, tenant_slug, "oidc") from e
    bruto_login = None
    if r["claim_login"]:
        bruto_login = claims.get(r["claim_login"])
    bruto_login = bruto_login or claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    try:
        login = _login_de_bruto(str(bruto_login))
    except ErroSSO as e:
        raise _falha_federada(request, e, tenant_slug, "oidc") from e
    return _provisionar_e_abrir(
        request, r, "oidc",
        sujeito=str(claims["sub"]),
        login=login,
        nome=str(claims.get("name") or login),
        email=str(claims["email"]) if claims.get("email") else None,
        grupos=_valores_texto(claims.get(r["claim_grupos"] or "groups")),
    )


# ================================================================== SAML
def _entidade_sp(request: Request, tenant_slug: str) -> str:
    """entityID do SP deste inquilino: a URL pública do PRÓPRIO documento de metadados (única por
    inquilino; é o valor que o administrador cadastra no IdP e o que a AudienceRestriction tem de trazer)."""
    return f"{_base(request)}api/login/saml/metadata?inquilino={tenant_slug}"


def _acs_sp(request: Request) -> str:
    return _base(request) + "api/login/saml/acs"


@router.get("/login/saml/metadata", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def saml_metadata(inquilino: str, request: Request):
    tenant_slug = inquilino.strip().lower()
    r = _provedor_de(tenant_slug, "saml")
    _provedor_habilitado(r, "saml", request)
    entidade = escapar_xml(_entidade_sp(request, tenant_slug), {'"': "&quot;"})
    acs = escapar_xml(_acs_sp(request), {'"': "&quot;"})
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{entidade}">'
        '<md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol" '
        'AuthnRequestsSigned="false" WantAssertionsSigned="true">'
        '<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>'
        f'<md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs}" index="0" isDefault="true"/>'
        "</md:SPSSODescriptor></md:EntityDescriptor>"
    )
    return Response(content=xml, media_type="application/samlmetadata+xml")


@router.get("/login/saml/iniciar", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def saml_iniciar(inquilino: str, request: Request):
    tenant_slug = inquilino.strip().lower()
    r = _provedor_de(tenant_slug, "saml")
    _provedor_habilitado(r, "saml", request)
    if not _url_externa_ok(r["idp_url_sso"]):
        request.state.resultado = "sem_configuracao"
        raise ErroAPI(503, "sso_sem_configuracao", "login federado não está configurado neste inquilino")
    pedido_id = "_" + secrets.token_hex(16)
    estado = secrets.token_urlsafe(24)
    instante = _agora().strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS_SAMLP}" xmlns:saml="{NS_SAML}" '
        f'ID="{pedido_id}" Version="2.0" IssueInstant="{instante}" '
        f'Destination="{escapar_xml(r["idp_url_sso"], {"\"": "&quot;"})}" '
        f'AssertionConsumerServiceURL="{escapar_xml(_acs_sp(request), {"\"": "&quot;"})}" '
        'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        f'<saml:Issuer>{escapar_xml(_entidade_sp(request, tenant_slug))}</saml:Issuer>'
        '<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified" '
        'AllowCreate="true"/></samlp:AuthnRequest>'
    )
    desflator = zlib.compressobj(9, zlib.DEFLATED, -15)  # DEFLATE cru (RFC 1951), como o binding manda
    comprimido = desflator.compress(xml.encode("utf-8")) + desflator.flush()
    _transacao_criar(r["tenant_id"], "saml", estado, None, None, pedido_id)
    parametros = urlencode({"SAMLRequest": base64.b64encode(comprimido).decode(), "RelayState": estado})
    return RedirectResponse(url=f"{r['idp_url_sso']}?{parametros}", status_code=302)


def _c14n(no) -> bytes:
    """Canonicalização exclusiva (exc-c14n) de um elemento, sem comentários."""
    saida = etree.tostring(no, method="c14n", exclusive=True, with_comments=False)
    return saida


def _resumir(dados: bytes, nome_resumo: str) -> bytes:
    return hashlib.new(nome_resumo, dados).digest()


def _validar_assinatura_assertion(assertion, chave_publica: RSAPublicKey) -> None:
    """Etapas 3-5 da docstring do módulo. Levanta ErroSSO em qualquer desvio; devolve None só com a
    assinatura envolvida da assertion verificada de ponta a ponta."""
    assinaturas = assertion.findall(f"{{{NS_DS}}}Signature")
    if len(assinaturas) != 1:
        raise ErroSSO(f"assertion_assinaturas:{len(assinaturas)}")
    assinatura = assinaturas[0]
    info = assinatura.find(f"{{{NS_DS}}}SignedInfo")
    if info is None:
        raise ErroSSO("assinatura_sem_signedinfo")
    metodo_c14n = info.find(f"{{{NS_DS}}}CanonicalizationMethod")
    if metodo_c14n is None or metodo_c14n.get("Algorithm") not in ALG_C14N:
        raise ErroSSO("c14n_nao_exclusivo")
    metodo_assinatura = info.find(f"{{{NS_DS}}}SignatureMethod")
    algoritmo = metodo_assinatura.get("Algorithm") if metodo_assinatura is not None else None
    if algoritmo not in ALG_ASSINATURA:
        raise ErroSSO(f"algoritmo_assinatura_recusado:{algoritmo!r}")
    referencias = info.findall(f"{{{NS_DS}}}Reference")
    if len(referencias) != 1:
        raise ErroSSO(f"referencias:{len(referencias)}")
    referencia = referencias[0]
    uri = referencia.get("URI") or ""
    id_assertion = assertion.get("ID") or ""
    if not id_assertion or uri != f"#{id_assertion}":
        raise ErroSSO("referencia_nao_aponta_para_a_assertion")
    transforms = referencia.find(f"{{{NS_DS}}}Transforms")
    permitidos = {ALG_ENVOLVIDA, *ALG_C14N}
    if transforms is not None:
        for t in transforms.findall(f"{{{NS_DS}}}Transform"):
            if t.get("Algorithm") not in permitidos:
                raise ErroSSO(f"transform_recusado:{t.get('Algorithm')!r}")
    metodo_resumo = referencia.find(f"{{{NS_DS}}}DigestMethod")
    nome_resumo = ALG_RESUMO.get(metodo_resumo.get("Algorithm") if metodo_resumo is not None else None)
    if nome_resumo is None:
        raise ErroSSO("algoritmo_resumo_recusado")
    valor_resumo = referencia.findtext(f"{{{NS_DS}}}DigestValue") or ""
    try:
        esperado = base64.b64decode(valor_resumo)
    except ValueError as e:
        raise ErroSSO("resumo_base64_invalido") from e
    # resumo da assertion SEM a assinatura (transform enveloped): remove o elemento antes de canonicalizar
    assertion.remove(assinatura)
    if _resumir(_c14n(assertion), nome_resumo) != esperado:
        raise ErroSSO("resumo_divergente")
    valor_assinatura = assinatura.findtext(f"{{{NS_DS}}}SignatureValue") or ""
    try:
        assinatura_bytes = base64.b64decode(valor_assinatura)
    except ValueError as e:
        raise ErroSSO("assinatura_base64_invalida") from e
    try:
        chave_publica.verify(
            assinatura_bytes, _c14n(info), padding.PKCS1v15(), ALG_ASSINATURA[algoritmo]()
        )
    except InvalidSignature as e:
        raise ErroSSO("assinatura_invalida") from e


def validar_resposta_saml(saml_response_b64: str, *, idp_entidade: str, idp_certificado_pem: str,
                          entidade_sp: str, acs_sp: str, pedido_id: str) -> dict:
    """Valida uma SAMLResponse (HTTP-POST binding) de ponta a ponta e devolve {"sujeito", "atributos"}.
    Toda recusa levanta ErroSSO com motivo interno; nada é devolvido parcialmente validado."""
    try:
        bruto = base64.b64decode(saml_response_b64)
    except ValueError as e:
        raise ErroSSO("resposta_base64_invalida") from e
    if len(bruto) > limites.SSO_RESPOSTA_MAX:
        raise ErroSSO(f"resposta_grande_demais:{len(bruto)}")
    analisador = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        raiz = etree.fromstring(bruto, analisador)
    except etree.XMLSyntaxError as e:
        raise ErroSSO("resposta_xml_invalido") from e
    if raiz.tag != f"{{{NS_SAMLP}}}Response":
        raise ErroSSO(f"raiz_inesperada:{raiz.tag!r}")
    assertions = raiz.findall(f"{{{NS_SAML}}}Assertion")
    if len(assertions) != 1:
        raise ErroSSO(f"assertions:{len(assertions)}")  # 0 = sem identidade; 2+ = wrapping (XSW)
    assertion = assertions[0]
    emissor = assertion.findtext(f"{{{NS_SAML}}}Issuer") or ""
    if emissor.strip() != idp_entidade:
        raise ErroSSO("emissor_divergente")
    try:
        certificado = x509.load_pem_x509_certificate(idp_certificado_pem.encode("utf-8"))
        chave = certificado.public_key()
    except ValueError as e:
        raise ErroSSO("certificado_idp_ilegivel", indisponivel=True) from e
    if not isinstance(chave, RSAPublicKey):
        raise ErroSSO("certificado_idp_nao_rsa", indisponivel=True)
    _validar_assinatura_assertion(assertion, chave)
    agora = _agora()
    folga = datetime.timedelta(seconds=limites.SSO_DESVIO_RELOGIO_S)
    condicoes = assertion.find(f"{{{NS_SAML}}}Conditions")
    if condicoes is None:
        raise ErroSSO("sem_condicoes")
    if condicoes.get("NotBefore") and agora < _instante(condicoes.get("NotBefore")) - folga:
        raise ErroSSO("ainda_nao_valida")
    if not condicoes.get("NotOnOrAfter"):
        raise ErroSSO("sem_notonorafter")
    if agora >= _instante(condicoes.get("NotOnOrAfter")) + folga:
        raise ErroSSO("assertion_expirada")
    restricoes = condicoes.findall(f"{{{NS_SAML}}}AudienceRestriction")
    if not restricoes:
        raise ErroSSO("sem_audience")
    for restricao in restricoes:
        audiencias = [a.text or "" for a in restricao.findall(f"{{{NS_SAML}}}Audience")]
        if entidade_sp not in audiencias:
            raise ErroSSO("audience_divergente")
    sujeito = assertion.find(f"{{{NS_SAML}}}Subject")
    if sujeito is None:
        raise ErroSSO("sem_sujeito")
    confirmacoes = sujeito.findall(f"{{{NS_SAML}}}SubjectConfirmation")
    portador = None
    for c in confirmacoes:
        if c.get("Method") == "urn:oasis:names:tc:SAML:2.0:cm:bearer":
            portador = c
    if portador is None:
        raise ErroSSO("sem_confirmacao_bearer")
    dados = portador.find(f"{{{NS_SAML}}}SubjectConfirmationData")
    if dados is None:
        raise ErroSSO("sem_dados_confirmacao")
    if dados.get("InResponseTo") != pedido_id:
        raise ErroSSO("inresponseto_divergente")
    if (dados.get("Recipient") or "") != acs_sp:
        raise ErroSSO("recipient_divergente")
    if not dados.get("NotOnOrAfter") or agora >= _instante(dados.get("NotOnOrAfter")) + folga:
        raise ErroSSO("confirmacao_expirada")
    nameid = sujeito.findtext(f"{{{NS_SAML}}}NameID") or ""
    if not nameid.strip():
        raise ErroSSO("sem_nameid")
    atributos: dict[str, list[str]] = {}
    declaracao = assertion.find(f"{{{NS_SAML}}}AttributeStatement")
    if declaracao is not None:
        for atributo in declaracao.findall(f"{{{NS_SAML}}}Attribute"):
            nome = atributo.get("Name") or ""
            valores = [v.text or "" for v in atributo.findall(f"{{{NS_SAML}}}AttributeValue")]
            atributos.setdefault(nome, []).extend(valores)
    return {"sujeito": nameid.strip(), "atributos": atributos}


def _primeiro(atributos: dict[str, list[str]], nomes: tuple[str, ...]) -> str | None:
    for nome in nomes:
        valores = atributos.get(nome)
        if valores and valores[0].strip():
            return valores[0].strip()
    return None


@router.post("/login/saml/acs", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def saml_acs(request: Request):
    # application/x-www-form-urlencoded parseado na mão: o ambiente não tem python-multipart (instalar
    # mexeria no venv compartilhado) e o corpo do POST binding é urlencoded por definição, nunca multipart
    corpo_bruto = (await request.body()).decode("utf-8", errors="replace")
    campos = dict(par.split("=", 1) for par in (p for p in corpo_bruto.split("&") if "=" in p))
    campos = {unquote_plus(k): unquote_plus(v) for k, v in campos.items()}
    saml_response = campos.get("SAMLResponse") or ""
    relay_state = (campos.get("RelayState") or "").strip()
    if not saml_response or not relay_state:
        request.state.resultado = "federacao_invalida"
        raise ErroAPI(401, "federacao_invalida", "não foi possível confirmar sua identidade no provedor")
    try:
        transacao = _transacao_consumir(relay_state, "saml")
    except ErroSSO:
        request.state.resultado = "federacao_invalida"
        raise ErroAPI(401, "federacao_invalida", "não foi possível confirmar sua identidade no provedor") from None
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_sso_de((SELECT slug FROM plat.tenant WHERE id = %s), 'saml')",
                    (transacao["tenant_id"],))
        r = cur.fetchone()
    if r is None or not r["habilitado"]:
        request.state.resultado = "externo_desabilitado"
        raise ErroAPI(403, "login_sso_desabilitado", "este inquilino não tem login por SAML habilitado")
    tenant_slug = r["tenant_slug"]
    try:
        validado = validar_resposta_saml(
            saml_response,
            idp_entidade=r["idp_entidade"],
            idp_certificado_pem=r["idp_certificado"],
            entidade_sp=_entidade_sp(request, tenant_slug),
            acs_sp=_acs_sp(request),
            pedido_id=transacao["pedido_id"],
        )
        atributos = validado["atributos"]
        bruto_login = None
        if r["claim_login"]:
            bruto_login = _primeiro(atributos, (r["claim_login"],))
        bruto_login = bruto_login or validado["sujeito"]
        login = _login_de_bruto(bruto_login)
    except ErroSSO as e:
        raise _falha_federada(request, e, tenant_slug, "saml") from e
    return _provisionar_e_abrir(
        request, r, "saml",
        sujeito=validado["sujeito"],
        login=login,
        nome=_primeiro(atributos, ATRIBUTOS_NOME) or login,
        email=_primeiro(atributos, ATRIBUTOS_EMAIL),
        grupos=atributos.get(r["claim_grupos"] or "groups", []),
    )


# ================================================================== configuração do provedor por inquilino
# (GET/PUT /api/org/sso/oidc e /api/org/sso/saml; privilégio org.integracoes, o mesmo que a ADR 0002 reservou
# para "SSO, SMTP, webhooks, CORS"). O segredo de cliente OIDC nunca é devolvido (só `tem_segredo`); o PUT o
# aceita em claro só para cifrar e gravar — omitido, preserva o anterior.
class ProvedorOidcEntrada(Modelo):
    habilitado: bool = True
    emissor: str = Field(min_length=8, max_length=250)
    cliente_id: str = Field(min_length=1, max_length=250)
    cliente_segredo: str | None = Field(default=None, max_length=250)
    claim_grupos: str = Field(default="groups", min_length=1, max_length=64)
    claim_login: str | None = Field(default=None, max_length=64)
    perfil_padrao: str | None = None
    mapa_grupo_perfil: dict[str, str] = Field(default_factory=dict)


class ProvedorSamlEntrada(Modelo):
    habilitado: bool = True
    idp_entidade: str = Field(min_length=1, max_length=250)
    idp_url_sso: str = Field(min_length=8, max_length=250)
    idp_certificado: str = Field(min_length=20, max_length=8192)
    claim_grupos: str = Field(default="groups", min_length=1, max_length=64)
    claim_login: str | None = Field(default=None, max_length=64)
    perfil_padrao: str | None = None
    mapa_grupo_perfil: dict[str, str] = Field(default_factory=dict)


class ProvedorSsoSaida(Saida):
    tipo: str
    habilitado: bool
    emissor: str | None
    cliente_id: str | None
    tem_segredo: bool
    idp_entidade: str | None
    idp_url_sso: str | None
    idp_certificado: str | None
    claim_grupos: str | None
    claim_login: str | None
    perfil_padrao: str | None
    mapa_grupo_perfil: dict[str, Any]


def _validar_mapa(perfil_padrao: str | None, mapa: dict[str, str]) -> None:
    if perfil_padrao is not None and perfil_padrao not in PERFIS_VALIDOS:
        raise ErroAPI(422, "validacao", f"perfil_padrao precisa ser um de {PERFIS_VALIDOS}", {"campo": "perfil_padrao"})
    for grupo, perfil in mapa.items():
        if perfil not in PERFIS_VALIDOS:
            raise ErroAPI(
                422, "validacao", f"mapa_grupo_perfil[{grupo!r}] precisa ser um de {PERFIS_VALIDOS}",
                {"campo": "mapa_grupo_perfil", "grupo": grupo},
            )


def _saida_de(r: dict | None, tipo: str) -> dict | None:
    if r is None:
        return None
    return {
        "tipo": tipo,
        "habilitado": r["habilitado"],
        "emissor": r["emissor"],
        "cliente_id": r["cliente_id"],
        "tem_segredo": bool(r["cliente_segredo_cifrado"]),
        "idp_entidade": r["idp_entidade"],
        "idp_url_sso": r["idp_url_sso"],
        "idp_certificado": r["idp_certificado"],
        "claim_grupos": r["claim_grupos"],
        "claim_login": r["claim_login"],
        "perfil_padrao": r["perfil_padrao"],
        "mapa_grupo_perfil": r["mapa_grupo_perfil"] or {},
    }


def _ler_config(auth: Auth, tipo: str):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.provedor_sso WHERE tenant_id = plat.tenant_atual() AND tipo = %s", (tipo,))
        r = cur.fetchone()
    return _saida_de(r, tipo)


def _gravar_config(request: Request, auth: Auth, tipo: str, corpo: ProvedorOidcEntrada | ProvedorSamlEntrada):
    _validar_mapa(corpo.perfil_padrao, corpo.mapa_grupo_perfil)
    segredo_cifrado = None
    if tipo == "oidc":
        if not _url_externa_ok(corpo.emissor):
            raise ErroAPI(422, "validacao", "emissor precisa ser https (ou laço local de teste)", {"campo": "emissor"})
        if corpo.cliente_segredo:
            segredo_cifrado = cifrar_segredo(corpo.cliente_segredo, settings.PLAT_SECRET)
        else:
            with db.db(auth.contexto()) as cur:
                cur.execute(
                    "SELECT cliente_segredo_cifrado FROM plat.provedor_sso "
                    "WHERE tenant_id = plat.tenant_atual() AND tipo = 'oidc'"
                )
                anterior = cur.fetchone()
            segredo_cifrado = anterior["cliente_segredo_cifrado"] if anterior else None
    else:
        if not _url_externa_ok(corpo.idp_url_sso):
            raise ErroAPI(422, "validacao", "idp_url_sso precisa ser https (ou laço local de teste)",
                          {"campo": "idp_url_sso"})
        try:
            certificado = x509.load_pem_x509_certificate(corpo.idp_certificado.encode("utf-8"))
            if not isinstance(certificado.public_key(), RSAPublicKey):
                raise ValueError("chave não RSA")
        except ValueError:
            raise ErroAPI(422, "validacao", "idp_certificado precisa ser um PEM X.509 com chave RSA",
                          {"campo": "idp_certificado"}) from None
    comuns = {
        "oidc": (corpo.emissor, corpo.cliente_id, segredo_cifrado, None, None, None),
        "saml": (None, None, None, corpo.idp_entidade, corpo.idp_url_sso, corpo.idp_certificado),
    }[tipo]
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                INSERT INTO plat.provedor_sso(tenant_id, tipo, habilitado, emissor, cliente_id,
                    cliente_segredo_cifrado, idp_entidade, idp_url_sso, idp_certificado, claim_grupos,
                    claim_login, perfil_padrao, mapa_grupo_perfil, criado_por, atualizado_por)
                VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (tenant_id, tipo) DO UPDATE SET
                    habilitado = EXCLUDED.habilitado, emissor = EXCLUDED.emissor,
                    cliente_id = EXCLUDED.cliente_id,
                    cliente_segredo_cifrado = EXCLUDED.cliente_segredo_cifrado,
                    idp_entidade = EXCLUDED.idp_entidade, idp_url_sso = EXCLUDED.idp_url_sso,
                    idp_certificado = EXCLUDED.idp_certificado, claim_grupos = EXCLUDED.claim_grupos,
                    claim_login = EXCLUDED.claim_login, perfil_padrao = EXCLUDED.perfil_padrao,
                    mapa_grupo_perfil = EXCLUDED.mapa_grupo_perfil,
                    atualizado_por = EXCLUDED.atualizado_por, atualizado_em = now()
                RETURNING *
                """,
                (
                    tipo, corpo.habilitado, *comuns, corpo.claim_grupos, corpo.claim_login,
                    corpo.perfil_padrao, json.dumps(corpo.mapa_grupo_perfil), auth.usuario_id, auth.usuario_id,
                ),
            )
            r = cur.fetchone()
            registrar_evento(
                cur, request, "org/sso_configurar", "provedor_sso", r["id"],
                {"tipo": tipo, "habilitado": r["habilitado"]},
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _saida_de(r, tipo)


@router.get("/org/sso/oidc", response_model=ProvedorSsoSaida | None,
            openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"})
def org_sso_ler_oidc(auth: Auth = autenticado("org.integracoes")):
    return _ler_config(auth, "oidc")


@router.put("/org/sso/oidc", response_model=ProvedorSsoSaida,
            openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"})
def org_sso_gravar_oidc(corpo: ProvedorOidcEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    return _gravar_config(request, auth, "oidc", corpo)


@router.get("/org/sso/saml", response_model=ProvedorSsoSaida | None,
            openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"})
def org_sso_ler_saml(auth: Auth = autenticado("org.integracoes")):
    return _ler_config(auth, "saml")


@router.put("/org/sso/saml", response_model=ProvedorSsoSaida,
            openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"})
def org_sso_gravar_saml(corpo: ProvedorSamlEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    return _gravar_config(request, auth, "saml", corpo)
