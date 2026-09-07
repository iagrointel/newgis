"""SAML 2.0 Web SSO por inquilino (item L0-08-b-saml; irmão do L0-08-a-oidc, mesma família L0-08-sso).

Módulo isolado no padrão de app/auth/oidc.py: valida a asserção no provedor externo e REAPROVEITA
`_abrir_sessao` (app/auth/rotas_login.py) a partir daí — cookie, evento `usuarios/entrar` e política de sessão
são os do login local. A identidade é a MESMA do OIDC: plat.usuario com origem='saml' e
sujeito_externo = '<entityId do IdP>#<NameID>', provisionada por plat.usuario_externo_provisionar (a função
que o oidc_provisionar passou a chamar). Só a configuração do provedor (plat.provedor_saml) é própria.

Biblioteca: python3-saml (OneLogin; MIT) sobre xmlsec (wheel com libxmlsec embutida) — assinatura XML-DSig,
XML Signature Wrapping, esquema XSD, EncryptedAssertion, metadado do SP assinado e validado contra o XSD do
SAML, SLO. Sempre `strict: True`; `wantMessagesSigned` e `wantAssertionsSigned` ligados (assinatura de resposta
E de asserção obrigatórias); algoritmos depreciados (SHA-1) recusados; desvio de relógio tolerado
limites.SAML_DESVIO_RELOGIO_S (10 min à frente = 401).

Fluxo:
  GET  /api/sso/saml/metadata?inquilino&provedor_id  metadado do SP (entityId = esta URL; assinado)
  GET  /api/sso/saml/iniciar?inquilino[&provedor_id][&proximo]   AuthnRequest assinado (HTTP-Redirect), transação
       de uso único (plat.saml_transacao, TTL 10 min) com o ID do pedido → 302 ao IdP
  POST /api/sso/saml/acs   SAMLResponse (HTTP-POST). SP-initiated: InResponseTo consome a transação.
       IdP-initiated: sem InResponseTo, o provedor vem da Audience (entityId do SP, único por provedor) ou do
       Issuer. Replay: o ID da asserção fica em plat.saml_assercao_usada até o NotOnOrAfter → 401 na 2ª vez.
  GET  /api/sso/saml/logout   encerra a sessão local e, quando ela nasceu por SAML e o IdP tem SLO, 302 com o
       LogoutRequest assinado (logout propagado SP → IdP); senão 204.
  GET|POST /api/sso/saml/slo   LogoutRequest vindo do IdP (encerra toda sessão local do NameID e responde
       LogoutResponse assinado) ou LogoutResponse do nosso LogoutRequest (apaga o cookie).
  GET/POST/PUT/DELETE /api/org/saml[/{id}]   configuração por inquilino (org.integracoes): metadado do IdP por
       URL, por XML ou por parâmetros; o par de chaves do SP é gerado aqui e a chave privada gravada cifrada.
O motivo específico de cada recusa só vai para o log; o corpo é sempre o mesmo 401 genérico."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import logging
import re
import secrets
import zlib
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from lxml import etree
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from pydantic import Field

from app import db, limites
from app.auth.comum import apagar_cookie, erro_do_banco, registrar_evento
from app.auth.ldap import PERFIS_VALIDOS, perfil_por_grupos
from app.auth.modelos import Modelo, Saida
from app.auth.oidc import _url_valida_https_ou_teste
from app.auth.politica import politica_de
from app.auth.rotas_login import _abrir_sessao
from app.auth.sessao import COOKIE, Auth, autenticado, resolver, sha256_hex
from app.conexao import seguranca
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.auth.saml")
router = APIRouter(prefix="/api", tags=["login"])
PREFIXO_CIFRA = "encsaml:v1:"
NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
}
# regra Esri de login SAML (E11-saml): só alfanumérico, '_', '.' e '@'
_RE_LOGIN = re.compile(r"^[A-Za-z0-9_.@]{1,120}$")
_RE_PROXIMO = re.compile(r"^/(?!/)[\w\-./?=&%]*$")
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=False)
OneLogin_Saml2_Constants.ALLOWED_CLOCK_DRIFT = limites.SAML_DESVIO_RELOGIO_S


# ---------------------------------------------------------------- cifra da chave privada do SP (mesmo esquema
# AES-GCM dos módulos irmãos; AAD própria: chave cifrada para SAML nunca decifra como segredo OIDC/LDAP)
def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"saml-sp-chave").digest()


def cifrar_chave(pem: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, pem.encode("utf-8"), b"plat-saml-sp-chave")
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar_chave(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("chave do SP sem o prefixo encsaml:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], b"plat-saml-sp-chave").decode("utf-8")


def gerar_par_sp(nome: str) -> tuple[str, str]:
    """(chave privada PEM, certificado base64 DER) RSA 2048 autoassinado por 10 anos — o certificado vai no
    metadado do SP; o IdP o usa para conferir o AuthnRequest/LogoutRequest e para cifrar a asserção."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeito = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nome[:64])])
    agora = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(sujeito)
        .issuer_name(sujeito)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(days=3650))
        .sign(chave, hashes.SHA256())
    )
    pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    der = cert.public_bytes(serialization.Encoding.DER)
    return pem, base64.b64encode(der).decode("ascii")


def cert_base64(valor: str) -> str:
    """Aceita PEM ou base64 puro; devolve só o base64 DER (formato que o python3-saml e o metadado usam)."""
    linhas = [ln.strip() for ln in (valor or "").splitlines() if ln.strip() and not ln.startswith("-----")]
    limpo = "".join(linhas).replace(" ", "")
    try:
        x509.load_der_x509_certificate(base64.b64decode(limpo))
    except Exception as e:  # noqa: BLE001 — qualquer certificado ilegível é a mesma recusa
        raise ErroAPI(
            422, "validacao", "certificado do IdP ilegível (PEM ou base64 DER)", {"campo": "idp_certificado"}
        ) from e
    return limpo


# ---------------------------------------------------------------- configuração do python3-saml por provedor
class ErroSaml(Exception):
    def __init__(self, motivo_interno: str):
        self.motivo_interno = motivo_interno
        super().__init__(motivo_interno)


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def urls_sp(base: str, slug: str, provedor_id: int) -> dict[str, str]:
    return {
        # um único parâmetro: o python3-saml grava o entityId no XML sem escapar '&'
        "entity_id": f"{base}/api/sso/saml/metadata?provedor_id={provedor_id}",
        "acs": f"{base}/api/sso/saml/acs",
        "slo": f"{base}/api/sso/saml/slo",
    }


def configuracao(provedor: dict, base: str, *, com_chave: bool = True) -> dict:
    u = urls_sp(base, provedor["tenant_slug"], provedor["provedor_id"])
    sp: dict[str, Any] = {
        "entityId": u["entity_id"],
        "assertionConsumerService": {"url": u["acs"], "binding": OneLogin_Saml2_Constants.BINDING_HTTP_POST},
        "singleLogoutService": {"url": u["slo"], "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT},
        "NameIDFormat": provedor["formato_nameid"],
        "x509cert": provedor["sp_certificado"],
    }
    if com_chave:
        try:
            sp["privateKey"] = decifrar_chave(provedor["sp_chave_privada_cifrada"], settings.PLAT_SECRET)
        except ValueError as e:
            raise ErroSaml("chave_do_sp_ilegivel") from e
    idp: dict[str, Any] = {
        "entityId": provedor["idp_entity_id"],
        "singleSignOnService": {
            "url": provedor["idp_sso_url"],
            "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
        },
        "x509certMulti": {
            "signing": list(provedor["idp_certificados"]),
            "encryption": list(provedor["idp_certificados"]),
        },
    }
    if provedor.get("idp_slo_url"):
        idp["singleLogoutService"] = {
            "url": provedor["idp_slo_url"],
            "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
        }
    return {
        "strict": True,
        "debug": False,
        "sp": sp,
        "idp": idp,
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": True,
            "logoutRequestSigned": True,
            "logoutResponseSigned": True,
            "signMetadata": True,
            "wantMessagesSigned": True,
            "wantAssertionsSigned": True,
            "wantAssertionsEncrypted": bool(provedor["assercao_cifrada"]),
            "wantNameId": True,
            "wantNameIdEncrypted": False,
            "wantAttributeStatement": False,
            "allowRepeatAttributeName": False,
            "requestedAuthnContext": False,
            "rejectUnsolicitedResponsesWithInResponseTo": False,
            "rejectDeprecatedAlgorithm": True,
            "signatureAlgorithm": OneLogin_Saml2_Constants.RSA_SHA256,
            "digestAlgorithm": OneLogin_Saml2_Constants.SHA256,
        },
    }


async def pedido_de(request: Request) -> dict:
    """Request do Starlette -> `request_data` do python3-saml. Corpo urlencoded lido à mão (python-multipart
    não está instalado)."""
    base = urlsplit(_base(request))
    post: dict[str, str] = {}
    if request.method == "POST":
        corpo = await request.body()
        if len(corpo) > limites.SAML_RESPOSTA_MAX:
            raise ErroAPI(413, "saml_resposta_grande", "mensagem SAML acima do limite")
        post = {k: v[0] for k, v in parse_qs(corpo.decode("utf-8", errors="replace"), keep_blank_values=True).items()}
    return {
        "https": "on" if base.scheme == "https" else "off",
        "http_host": base.netloc,
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": post,
        "query_string": request.url.query,
    }


def _tenant_publico(slug: str) -> dict:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.tenant_publico(%s)", (slug,))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
    return r


def _provedor_por_id(provedor_id: int) -> dict | None:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_saml_por_id(%s)", (provedor_id,))
        return cur.fetchone()


def _provedor_do_inquilino(slug: str | None, provedor_id: int | None) -> dict:
    """Provedor habilitado: por id (o entityId do SP carrega só o id), por inquilino (o primeiro na ordem) ou os
    dois (o id tem de pertencer ao inquilino)."""
    if slug is None:
        if provedor_id is None:
            raise ErroAPI(422, "validacao", "informe inquilino ou provedor_id")
        p = _provedor_por_id(provedor_id)
        if p is None or not p["habilitado"]:
            raise ErroAPI(404, "saml_provedor_inexistente", "provedor SAML inexistente ou desabilitado")
        if not p["tenant_ativo"]:
            raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
        return p
    t = _tenant_publico(slug)
    if not t["ativo"]:
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedores_saml_de(%s)", (slug,))
        lista = list(cur.fetchall())
    if not lista:
        raise ErroAPI(404, "saml_sem_configuracao", "este inquilino não tem login SAML habilitado")
    escolhido = next((p for p in lista if p["provedor_id"] == provedor_id), None) if provedor_id else lista[0]
    if escolhido is None:
        raise ErroAPI(404, "saml_provedor_inexistente", "provedor SAML inexistente ou desabilitado neste inquilino")
    p = _provedor_por_id(escolhido["provedor_id"])
    if p is None:
        raise ErroAPI(404, "saml_provedor_inexistente", "provedor SAML inexistente ou desabilitado neste inquilino")
    return p


def _falha(request: Request, motivo_interno: str, publico: str = "saml_invalido") -> ErroAPI:
    log.warning("login SAML recusado: %s", motivo_interno)
    request.state.resultado = "saml_recusado"
    return ErroAPI(401, publico, "não foi possível concluir o login pela organização")


# ================================================================== metadado do SP
@router.get("/sso/saml/metadata", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def sso_saml_metadata(request: Request, inquilino: str | None = None, provedor_id: int | None = None):
    p = _provedor_do_inquilino(inquilino.strip().lower() if inquilino else None, provedor_id)
    try:
        cfg = OneLogin_Saml2_Settings(configuracao(p, _base(request)), sp_validation_only=True)
        xml = cfg.get_sp_metadata()
        erros = cfg.validate_metadata(xml)
    except ErroSaml as e:
        raise ErroAPI(503, "saml_indisponivel", "provedor de login indisponível; tente o login local") from e
    if erros:
        log.error("metadado do SP inválido (provedor %s): %s", p["provedor_id"], erros)
        raise ErroAPI(503, "saml_indisponivel", "metadado do SP inválido; fale com o operador")
    return Response(content=xml, media_type="application/samlmetadata+xml", headers={"Cache-Control": "no-store"})


# ================================================================== SP-initiated
@router.get("/sso/saml/iniciar", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def sso_saml_iniciar(
    inquilino: str, request: Request, provedor_id: int | None = None, proximo: str | None = None
):
    p = _provedor_do_inquilino(inquilino.strip().lower(), provedor_id)
    relay = proximo if proximo and _RE_PROXIMO.match(proximo) and len(proximo) <= 500 else "/"
    try:
        auth = OneLogin_Saml2_Auth(await pedido_de(request), configuracao(p, _base(request)))
        destino = auth.login(return_to=relay)
    except ErroSaml as e:
        raise ErroAPI(503, "saml_indisponivel", "provedor de login indisponível; tente o login local") from e
    with db.db() as cur:
        cur.execute(
            "SELECT plat.saml_transacao_abrir(%s, 'login', %s, %s, %s)",
            (auth.get_last_request_id(), p["provedor_id"], p["tenant_id"], relay),
        )
    return RedirectResponse(destino, status_code=302)


def _ler_resposta(saml_response_b64: str) -> etree._Element:
    """Só o suficiente para achar Issuer/InResponseTo/Audience ANTES de saber o provedor; a validação de verdade
    (assinaturas, XSD, tempos, audiência) é do python3-saml, com a configuração do provedor escolhido."""
    try:
        bruto = base64.b64decode(saml_response_b64, validate=False)
    except (ValueError, TypeError) as e:
        raise ErroSaml("saml_response_nao_e_base64") from e
    if len(bruto) > limites.SAML_RESPOSTA_MAX:
        raise ErroSaml("saml_response_grande")
    try:
        raiz = etree.fromstring(bruto, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise ErroSaml(f"xml_invalido:{str(e)[:80]}") from e
    if raiz.tag != f"{{{NS['samlp']}}}Response":
        raise ErroSaml("raiz_nao_e_response")
    return raiz


def _provedor_da_resposta(raiz: etree._Element) -> tuple[dict, dict | None]:
    """(provedor, transação | None). InResponseTo → transação de uso único (SP-initiated). Sem ela
    (IdP-initiated): Audience da asserção em claro tem o entityId do SP, que carrega o provedor_id; por fim
    o Issuer, quando aponta para um único provedor habilitado."""
    in_response_to = raiz.get("InResponseTo")
    if in_response_to:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.saml_transacao_consumir(%s)", (in_response_to,))
            tr = cur.fetchone()
        if tr is None or tr["tipo"] != "login":
            raise ErroSaml(f"in_response_to_desconhecido_ou_reusado:{in_response_to[:12]}")
        p = _provedor_por_id(tr["provedor_id"])
        if p is None:
            raise ErroSaml("provedor_da_transacao_sumiu")
        return p, tr
    for aud in raiz.iterfind(".//saml:Assertion/saml:Conditions/saml:AudienceRestriction/saml:Audience", NS):
        q = parse_qs(urlsplit((aud.text or "").strip()).query)
        if q.get("provedor_id", [""])[0].isdigit():
            p = _provedor_por_id(int(q["provedor_id"][0]))
            if p is not None:
                return p, None
    emissor = raiz.findtext("saml:Issuer", namespaces=NS)
    if emissor:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.provedores_saml_por_issuer(%s)", (emissor.strip(),))
            candidatos = list(cur.fetchall())
        if len(candidatos) == 1:
            p = _provedor_por_id(candidatos[0]["provedor_id"])
            if p is not None:
                return p, None
        if len(candidatos) > 1:
            raise ErroSaml("issuer_ambiguo_sem_in_response_to")
    raise ErroSaml("provedor_nao_identificado")


def _texto_atributo(atributos: dict, nome: str | None) -> str | None:
    if not nome:
        return None
    v = atributos.get(nome)
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v).strip() if v not in (None, "") else None


def _grupos(atributos: dict, nome: str) -> list[str]:
    v = atributos.get(nome) or []
    if isinstance(v, str):
        v = [v]
    return [str(x) for x in v]


@router.post("/sso/saml/acs", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def sso_saml_acs(request: Request, resposta: Response):
    pedido = await pedido_de(request)
    saml_response = pedido["post_data"].get("SAMLResponse")
    if not saml_response:
        raise _falha(request, "saml_response_ausente")
    try:
        raiz = _ler_resposta(saml_response)
        p, transacao = _provedor_da_resposta(raiz)
    except ErroSaml as e:
        raise _falha(request, e.motivo_interno) from e
    if not p["habilitado"]:
        raise _falha(request, "provedor_desabilitado")
    if not p["tenant_ativo"]:
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    try:
        auth = OneLogin_Saml2_Auth(pedido, configuracao(p, _base(request)))
    except ErroSaml as e:
        raise ErroAPI(503, "saml_indisponivel", "provedor de login indisponível; tente o login local") from e
    request_id = raiz.get("InResponseTo") if transacao else None
    try:
        auth.process_response(request_id=request_id)
    except Exception as e:  # noqa: BLE001 — a biblioteca levanta OneLogin_Saml2_Error/ValidationError variados
        raise _falha(request, f"process_response:{str(e)[:160]}") from e
    if auth.get_errors() or not auth.is_authenticated():
        raise _falha(request, f"{auth.get_errors()}:{(auth.get_last_error_reason() or '')[:200]}")
    if p["assercao_cifrada"] and raiz.find("saml:EncryptedAssertion", NS) is None:
        raise _falha(request, "assercao_em_claro_com_cifra_exigida")
    id_assercao = auth.get_last_assertion_id()
    expira = auth.get_last_assertion_not_on_or_after()
    expira_ts = dt.datetime.fromtimestamp(expira, dt.UTC) if expira else None
    with db.db() as cur:
        cur.execute("SELECT plat.saml_assercao_registrar(%s, %s, %s) AS nova", (p["tenant_id"], id_assercao, expira_ts))
        if not cur.fetchone()["nova"]:
            raise _falha(request, f"assercao_reutilizada:{(id_assercao or '')[:12]}", "assercao_reutilizada")
    atributos = auth.get_attributes() or {}
    name_id = (auth.get_nameid() or "").strip()
    login = (_texto_atributo(atributos, p["atributo_login"]) or name_id).lower()
    if not _RE_LOGIN.match(login):
        raise _falha(request, f"login_fora_da_regra:{login[:40]!r}", "nameid_invalido")
    email = _texto_atributo(atributos, p["atributo_email"])
    nome = _texto_atributo(atributos, p["atributo_nome"]) or (email.split("@")[0] if email else login)
    perfil = perfil_por_grupos(
        _grupos(atributos, p["atributo_grupos"]), p["mapa_grupo_perfil"] or {}, p["perfil_padrao"]
    )
    if perfil is None:
        request.state.resultado = "sem_grupo_mapeado"
        raise ErroAPI(
            403,
            "sem_grupo_mapeado",
            "nenhum grupo do provedor está mapeado para um perfil desta plataforma; fale com o administrador",
        )
    sujeito_externo = f"{p['idp_entity_id']}#{name_id}"
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT * FROM plat.usuario_externo_provisionar(%s, 'saml', %s, %s, %s, %s, %s, true)",
                (p["tenant_id"], login, nome[:200], email, perfil, sujeito_externo),
            )
            prov = cur.fetchone()
            cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (p["tenant_slug"], login))
            linha = cur.fetchone()
    except psycopg2.errors.RaiseException as e:
        if (e.diag.message_primary or "").strip() == "login_em_uso_local":
            raise _falha(request, "login_em_uso_local", "login_em_uso_local") from e
        raise erro_do_banco(e) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    if linha is None:
        raise _falha(request, "provisionamento_sem_login_correspondente")
    ctx = db.Contexto(linha["tenant_id"], linha["usuario_id"], login)
    with db.db(ctx) as cur:
        registrar_evento(
            cur,
            request,
            "usuarios/criar" if prov["criado"] else "usuarios/atualizar",
            "usuario",
            linha["usuario_id"],
            {"origem": "saml", "perfil": perfil, "perfil_anterior": prov["perfil_anterior"]},
        )
    _abrir_sessao(
        request, resposta, ctx, linha["usuario_id"], politica_de(linha["config"], p["tenant_slug"]), "saml", None
    )
    sessao_hash = getattr(getattr(request.state, "auth", None), "sessao_hash", None)
    if sessao_hash:
        with db.db() as cur:
            cur.execute(
                "SELECT plat.saml_sessao_abrir(%s, %s, %s, %s, %s, %s)",
                (
                    sessao_hash,
                    p["provedor_id"],
                    p["tenant_id"],
                    name_id,
                    auth.get_nameid_format(),
                    auth.get_session_index(),
                ),
            )
    relay = (transacao or {}).get("relay") or pedido["post_data"].get("RelayState") or "/"
    if not _RE_PROXIMO.match(relay or ""):
        relay = "/"
    destino = RedirectResponse(relay, status_code=303)
    for chave, valor in resposta.headers.items():  # o cookie de sessão emitido por _abrir_sessao
        if chave.lower() == "set-cookie":
            destino.headers.append("set-cookie", valor)
    return destino


# ================================================================== logout propagado
@router.get("/sso/saml/logout", openapi_extra={"x-auth": "S", "x-privilegio": "proprio"})
async def sso_saml_logout(request: Request):
    """Encerra a sessão local sempre; quando ela nasceu por SAML e o IdP tem SLO, 302 com o LogoutRequest assinado
    (o navegador leva a mensagem ao IdP, que encerra a sessão dele e volta por /sso/saml/slo); senão 204."""
    cookie = request.cookies.get(COOKIE)
    destino: str | None = None
    if cookie:
        try:
            auth = resolver(request)
        except ErroAPI:
            auth = None
        hash_sessao = auth.sessao_hash if auth is not None else sha256_hex(cookie)
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.saml_sessao_por_hash(%s)", (hash_sessao,))
            s = cur.fetchone()
        if s is not None:
            p = _provedor_por_id(s["provedor_id"])
            if p is not None and p.get("idp_slo_url"):
                try:
                    a = OneLogin_Saml2_Auth(await pedido_de(request), configuracao(p, _base(request)))
                    destino = a.logout(
                        return_to=_base(request) + "/",
                        name_id=s["name_id"],
                        session_index=s["session_index"],
                        name_id_format=s["name_id_format"],
                    )
                    with db.db() as cur:
                        cur.execute(
                            "SELECT plat.saml_transacao_abrir(%s, 'logout', %s, %s, %s)",
                            (a.get_last_request_id(), p["provedor_id"], p["tenant_id"], "/"),
                        )
                except ErroSaml as e:
                    log.warning("logout SAML sem propagação: %s", e.motivo_interno)
        if auth is not None:
            with db.db(auth.contexto()) as cur:
                registrar_evento(cur, request, "usuarios/sair", "usuario", auth.usuario_id)
        with db.db() as cur:
            cur.execute("SELECT plat.auth_sessao_encerrar(%s)", (hash_sessao,))
            cur.execute("SELECT plat.saml_sessao_apagar(%s)", (hash_sessao,))
    request.state.resultado = "logout"
    resposta = RedirectResponse(destino, status_code=302) if destino else Response(status_code=204)
    apagar_cookie(resposta, request)
    return resposta


def _ler_mensagem_slo(pedido: dict) -> tuple[str, etree._Element]:
    """('request'|'response', raiz) da mensagem SLO, por Redirect (deflate) ou POST."""
    dados = (
        pedido["get_data"]
        if pedido["get_data"].get("SAMLRequest") or pedido["get_data"].get("SAMLResponse")
        else pedido["post_data"]
    )
    bruto_b64 = dados.get("SAMLRequest") or dados.get("SAMLResponse")
    if not bruto_b64:
        raise ErroSaml("mensagem_slo_ausente")
    try:
        bruto = base64.b64decode(bruto_b64)
        if dados is pedido["get_data"]:
            bruto = zlib.decompress(bruto, -15)
    except (ValueError, TypeError, zlib.error) as e:
        raise ErroSaml("mensagem_slo_ilegivel") from e
    if len(bruto) > limites.SAML_RESPOSTA_MAX:
        raise ErroSaml("mensagem_slo_grande")
    try:
        raiz = etree.fromstring(bruto, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise ErroSaml("mensagem_slo_xml_invalido") from e
    if raiz.tag == f"{{{NS['samlp']}}}LogoutRequest":
        return "request", raiz
    if raiz.tag == f"{{{NS['samlp']}}}LogoutResponse":
        return "response", raiz
    raise ErroSaml("mensagem_slo_desconhecida")


async def _slo(request: Request):
    pedido = await pedido_de(request)
    try:
        tipo, raiz = _ler_mensagem_slo(pedido)
    except ErroSaml as e:
        raise _falha(request, e.motivo_interno) from e
    if tipo == "response":
        in_response_to = raiz.get("InResponseTo") or ""
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.saml_transacao_consumir(%s)", (in_response_to,))
            tr = cur.fetchone()
        if tr is None or tr["tipo"] != "logout":
            raise _falha(request, "logout_response_sem_transacao")
        p = _provedor_por_id(tr["provedor_id"])
        if p is None:
            raise _falha(request, "provedor_sumiu")
        try:
            a = OneLogin_Saml2_Auth(pedido, configuracao(p, _base(request)))
            a.process_slo(keep_local_session=True, request_id=in_response_to)
        except Exception as e:  # noqa: BLE001
            raise _falha(request, f"process_slo:{str(e)[:160]}") from e
        if a.get_errors():
            raise _falha(request, f"{a.get_errors()}:{(a.get_last_error_reason() or '')[:200]}")
        resposta = RedirectResponse("/", status_code=302)
        apagar_cookie(resposta, request)
        request.state.resultado = "logout"
        return resposta
    # LogoutRequest do IdP: acha o provedor pelo Issuer (um por inquilino) e encerra as sessões do NameID
    emissor = (raiz.findtext("saml:Issuer", namespaces=NS) or "").strip()
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedores_saml_por_issuer(%s)", (emissor,))
        candidatos = list(cur.fetchall())
    ultimo_erro = "sem_provedor_para_issuer"
    for c in candidatos:
        p = _provedor_por_id(c["provedor_id"])
        if p is None:
            continue
        try:
            a = OneLogin_Saml2_Auth(pedido, configuracao(p, _base(request)))
            encerradas = {"n": 0}

            def apagar(_p=p, _a=a, _n=encerradas):
                with db.db() as cur:
                    cur.execute(
                        "SELECT plat.saml_sessao_encerrar(%s, %s, %s) AS n",
                        (_p["provedor_id"], _a.get_nameid(), _a.get_session_index()),
                    )
                    _n["n"] = cur.fetchone()["n"]

            destino = a.process_slo(keep_local_session=False, delete_session_cb=apagar)
        except Exception as e:  # noqa: BLE001
            ultimo_erro = f"process_slo:{str(e)[:160]}"
            continue
        if a.get_errors():
            ultimo_erro = f"{a.get_errors()}:{(a.get_last_error_reason() or '')[:200]}"
            continue
        log.info(
            "logout SAML vindo do IdP: %s sessão(ões) encerrada(s) (provedor %s)", encerradas["n"], p["provedor_id"]
        )
        request.state.resultado = "logout"
        resposta = RedirectResponse(destino, status_code=302) if destino else Response(status_code=204)
        apagar_cookie(resposta, request)
        return resposta
    raise _falha(request, ultimo_erro)


@router.get("/sso/saml/slo", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def sso_saml_slo_get(request: Request):
    return await _slo(request)


@router.post("/sso/saml/slo", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def sso_saml_slo_post(request: Request):
    return await _slo(request)


# ================================================================== configuração por inquilino (/api/org/saml)
class ProvedorSamlEntrada(Modelo):
    habilitado: bool = True
    rotulo: str = Field(default="Entrar com a organização (SAML)", min_length=1, max_length=120)
    ordem: int = 0
    metadado_url: str | None = Field(default=None, max_length=1000)
    metadado_xml: str | None = Field(default=None, max_length=limites.SAML_METADADO_MAX)
    idp_entity_id: str | None = Field(default=None, max_length=500)
    idp_sso_url: str | None = Field(default=None, max_length=1000)
    idp_slo_url: str | None = Field(default=None, max_length=1000)
    idp_certificado: str | None = Field(default=None, max_length=10000)
    assercao_cifrada: bool = False
    formato_nameid: str = Field(default="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified", max_length=200)
    atributo_login: str | None = Field(default=None, max_length=200)
    atributo_email: str = Field(default="email", min_length=1, max_length=200)
    atributo_nome: str = Field(default="name", min_length=1, max_length=200)
    atributo_grupos: str = Field(default="groups", min_length=1, max_length=200)
    perfil_padrao: str | None = None
    mapa_grupo_perfil: dict[str, str] = Field(default_factory=dict)


class ProvedorSamlSaida(Saida):
    id: int
    habilitado: bool
    rotulo: str
    ordem: int
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: str | None
    idp_certificados: list[str]
    idp_metadado_url: str | None
    sp_certificado: str
    sp_metadata_url: str
    assercao_cifrada: bool
    formato_nameid: str
    atributo_login: str | None
    atributo_email: str
    atributo_nome: str
    atributo_grupos: str
    perfil_padrao: str | None
    mapa_grupo_perfil: dict[str, Any]


def _buscar_metadado(url: str) -> str:
    """Metadado do IdP por URL: https (ou loopback fora de produção), sem IP privado (defesa SSRF de
    app.conexao.seguranca), corpo limitado."""
    if not _url_valida_https_ou_teste(url):
        raise ErroAPI(
            422,
            "validacao",
            "metadado_url precisa ser https:// (http:// só em loopback fora de produção)",
            {"campo": "metadado_url"},
        )
    host = urlsplit(url).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1") and settings.PLAT_AMBIENTE != "producao":
        try:
            r = httpx.get(url, timeout=limites.SAML_METADADO_TIMEOUT_S, follow_redirects=False)
        except httpx.HTTPError as e:
            raise ErroAPI(422, "metadado_inacessivel", f"não foi possível ler o metadado: {e}") from e
        if r.status_code != 200 or len(r.content) > limites.SAML_METADADO_MAX:
            raise ErroAPI(422, "metadado_inacessivel", f"metadado respondeu {r.status_code}")
        return r.text
    res = seguranca.buscar_seguro(
        url,
        timeout_conectar=limites.SAML_METADADO_TIMEOUT_S,
        timeout_ler=limites.SAML_METADADO_TIMEOUT_S,
        max_bytes=limites.SAML_METADADO_MAX,
        guardar_corpo=True,
    )
    if not res.ok or res.status != 200:
        raise ErroAPI(422, "metadado_inacessivel", f"não foi possível ler o metadado: {res.mensagem or res.status}")
    return res.corpo.decode("utf-8", errors="replace")


def _idp_de(corpo: ProvedorSamlEntrada) -> dict:
    """{entity_id, sso_url, slo_url, certificados, metadado_url, metadado_xml} a partir de UMA das três fontes."""
    fontes = [f for f in (corpo.metadado_url, corpo.metadado_xml, corpo.idp_entity_id) if f]
    if len(fontes) != 1:
        raise ErroAPI(
            422,
            "validacao",
            "informe exatamente uma fonte: metadado_url, metadado_xml ou os parâmetros do IdP",
            {"campo": "metadado_url"},
        )
    if corpo.idp_entity_id:
        if not corpo.idp_sso_url or not corpo.idp_certificado:
            raise ErroAPI(422, "validacao", "parâmetros do IdP exigem idp_entity_id, idp_sso_url e idp_certificado")
        if not _url_valida_https_ou_teste(corpo.idp_sso_url):
            raise ErroAPI(422, "validacao", "idp_sso_url precisa ser https://", {"campo": "idp_sso_url"})
        return {
            "entity_id": corpo.idp_entity_id.strip(),
            "sso_url": corpo.idp_sso_url.strip(),
            "slo_url": (corpo.idp_slo_url or "").strip() or None,
            "certificados": [cert_base64(corpo.idp_certificado)],
            "metadado_url": None,
            "metadado_xml": None,
        }
    xml = _buscar_metadado(corpo.metadado_url) if corpo.metadado_url else corpo.metadado_xml
    try:
        lido = OneLogin_Saml2_IdPMetadataParser.parse(xml)
    except Exception as e:  # noqa: BLE001 — XML ilegível, sem IdP, sem certificado: mesma recusa
        raise ErroAPI(422, "metadado_invalido", f"metadado do IdP ilegível: {str(e)[:200]}") from e
    idp = (lido or {}).get("idp") or {}
    certs = []
    if idp.get("x509certMulti"):
        certs = list(idp["x509certMulti"].get("signing") or [])
    elif idp.get("x509cert"):
        certs = [idp["x509cert"]]
    if not idp.get("entityId") or not (idp.get("singleSignOnService") or {}).get("url") or not certs:
        raise ErroAPI(422, "metadado_invalido", "metadado do IdP sem entityId, SSO por HTTP-Redirect ou certificado")
    return {
        "entity_id": idp["entityId"],
        "sso_url": idp["singleSignOnService"]["url"],
        "slo_url": (idp.get("singleLogoutService") or {}).get("url"),
        "certificados": [cert_base64(c) for c in certs],
        "metadado_url": corpo.metadado_url,
        "metadado_xml": xml,
    }


def _validar_perfis(corpo: ProvedorSamlEntrada) -> None:
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


def _saida_de(r: dict, request: Request, slug: str) -> dict:
    return {
        "id": r["id"],
        "habilitado": r["habilitado"],
        "rotulo": r["rotulo"],
        "ordem": r["ordem"],
        "idp_entity_id": r["idp_entity_id"],
        "idp_sso_url": r["idp_sso_url"],
        "idp_slo_url": r["idp_slo_url"],
        "idp_certificados": list(r["idp_certificados"] or []),
        "idp_metadado_url": r["idp_metadado_url"],
        "sp_certificado": r["sp_certificado"],
        "sp_metadata_url": urls_sp(_base(request), slug, r["id"])["entity_id"],
        "assercao_cifrada": r["assercao_cifrada"],
        "formato_nameid": r["formato_nameid"],
        "atributo_login": r["atributo_login"],
        "atributo_email": r["atributo_email"],
        "atributo_nome": r["atributo_nome"],
        "atributo_grupos": r["atributo_grupos"],
        "perfil_padrao": r["perfil_padrao"],
        "mapa_grupo_perfil": r["mapa_grupo_perfil"] or {},
    }


ORG = {"x-auth": "S/T", "x-privilegio": "org.integracoes"}


@router.get("/org/saml", response_model=list[ProvedorSamlSaida], openapi_extra=ORG)
def org_saml_listar(request: Request, auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.provedor_saml WHERE tenant_id = plat.tenant_atual() ORDER BY ordem, id")
        return [_saida_de(r, request, auth.tenant_slug) for r in cur.fetchall()]


@router.post("/org/saml", status_code=201, response_model=ProvedorSamlSaida, openapi_extra=ORG)
def org_saml_criar(corpo: ProvedorSamlEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    _validar_perfis(corpo)
    idp = _idp_de(corpo)
    chave_pem, cert = gerar_par_sp(f"plat-{auth.tenant_slug}-saml")
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                INSERT INTO plat.provedor_saml(tenant_id, habilitado, rotulo, ordem, idp_entity_id, idp_sso_url,
                    idp_slo_url, idp_certificados, idp_metadado_url, idp_metadado_xml, sp_chave_privada_cifrada,
                    sp_certificado, assercao_cifrada, formato_nameid, atributo_login, atributo_email, atributo_nome,
                    atributo_grupos, perfil_padrao, mapa_grupo_perfil, criado_por, atualizado_por)
                VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s) RETURNING *
                """,
                (
                    corpo.habilitado,
                    corpo.rotulo,
                    corpo.ordem,
                    idp["entity_id"],
                    idp["sso_url"],
                    idp["slo_url"],
                    idp["certificados"],
                    idp["metadado_url"],
                    idp["metadado_xml"],
                    cifrar_chave(chave_pem, settings.PLAT_SECRET),
                    cert,
                    corpo.assercao_cifrada,
                    corpo.formato_nameid,
                    corpo.atributo_login,
                    corpo.atributo_email,
                    corpo.atributo_nome,
                    corpo.atributo_grupos,
                    corpo.perfil_padrao,
                    psycopg2.extras.Json(corpo.mapa_grupo_perfil),
                    auth.usuario_id,
                    auth.usuario_id,
                ),
            )
            r = cur.fetchone()
            registrar_evento(
                cur,
                request,
                "org/saml_configurar",
                "provedor_saml",
                r["id"],
                {
                    "idp_entity_id": r["idp_entity_id"],
                    "fonte": "url" if corpo.metadado_url else "xml" if corpo.metadado_xml else "parametros",
                },
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _saida_de(r, request, auth.tenant_slug)


@router.put("/org/saml/{provedor_id}", response_model=ProvedorSamlSaida, openapi_extra=ORG)
def org_saml_atualizar(
    provedor_id: int, corpo: ProvedorSamlEntrada, request: Request, auth: Auth = autenticado("org.integracoes")
):
    _validar_perfis(corpo)
    idp = _idp_de(corpo)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                UPDATE plat.provedor_saml
                SET habilitado = %s, rotulo = %s, ordem = %s, idp_entity_id = %s, idp_sso_url = %s,
                    idp_slo_url = %s, idp_certificados = %s, idp_metadado_url = %s, idp_metadado_xml = %s,
                    assercao_cifrada = %s, formato_nameid = %s, atributo_login = %s, atributo_email = %s,
                    atributo_nome = %s, atributo_grupos = %s, perfil_padrao = %s, mapa_grupo_perfil = %s::jsonb,
                    atualizado_por = %s, atualizado_em = now()
                WHERE id = %s AND tenant_id = plat.tenant_atual() RETURNING *
                """,
                (
                    corpo.habilitado,
                    corpo.rotulo,
                    corpo.ordem,
                    idp["entity_id"],
                    idp["sso_url"],
                    idp["slo_url"],
                    idp["certificados"],
                    idp["metadado_url"],
                    idp["metadado_xml"],
                    corpo.assercao_cifrada,
                    corpo.formato_nameid,
                    corpo.atributo_login,
                    corpo.atributo_email,
                    corpo.atributo_nome,
                    corpo.atributo_grupos,
                    corpo.perfil_padrao,
                    psycopg2.extras.Json(corpo.mapa_grupo_perfil),
                    auth.usuario_id,
                    provedor_id,
                ),
            )
            r = cur.fetchone()
            if r is None:
                raise ErroAPI(404, "saml_provedor_inexistente", "provedor SAML inexistente")
            registrar_evento(
                cur, request, "org/saml_configurar", "provedor_saml", r["id"], {"idp_entity_id": r["idp_entity_id"]}
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _saida_de(r, request, auth.tenant_slug)


@router.delete("/org/saml/{provedor_id}", status_code=204, response_class=Response, openapi_extra=ORG)
def org_saml_remover(provedor_id: int, request: Request, auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "DELETE FROM plat.provedor_saml WHERE id = %s AND tenant_id = plat.tenant_atual() RETURNING id",
            (provedor_id,),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "saml_provedor_inexistente", "provedor SAML inexistente")
        registrar_evento(cur, request, "org/saml_remover", "provedor_saml", provedor_id)
    return Response(status_code=204)
