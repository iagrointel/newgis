"""IdP SAML sintético para os testes do item L0-08-b: par de chaves gerado NA HORA (nada de chave privada no
repositório público), metadado de IdP, e um construtor de `Response` com `Assertion` que assina (XML-DSig via
python3-saml/xmlsec) a asserção e/ou a resposta, cifra a asserção (EncryptedAssertion, AES-256-CBC + RSA-OAEP
via xmlsec) e permite deslocar o relógio, trocar a chave, duplicar a asserção (XML Signature Wrapping) e
repetir o mesmo ID (replay). Cada forma de forja é um caso do portão/refutação."""

from __future__ import annotations

import base64
import datetime as dt
import secrets
from dataclasses import dataclass

import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from onelogin.saml2.utils import OneLogin_Saml2_Utils

NS_SAML = "urn:oasis:names:tc:SAML:2.0:assertion"
NS_SAMLP = "urn:oasis:names:tc:SAML:2.0:protocol"


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pem(cert_b64: str) -> str:
    return "-----BEGIN CERTIFICATE-----\n" + cert_b64 + "\n-----END CERTIFICATE-----\n"


@dataclass
class IdpFalso:
    entity_id: str
    sso_url: str
    slo_url: str
    chave_pem: str
    cert_b64: str

    @classmethod
    def novo(cls, entity_id: str = "https://idp-teste.invalido/saml") -> IdpFalso:
        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp-teste")])
        agora = dt.datetime.now(dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(nome)
            .issuer_name(nome)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(minutes=5))
            .not_valid_after(agora + dt.timedelta(days=30))
            .sign(chave, hashes.SHA256())
        )
        pem = chave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode("ascii")
        return cls(
            entity_id,
            entity_id + "/sso",
            entity_id + "/slo",
            pem,
            base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii"),
        )

    def metadado(self) -> str:
        return f"""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" entityID="{self.entity_id}">
  <md:IDPSSODescriptor WantAuthnRequestsSigned="false" protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing"><ds:KeyInfo><ds:X509Data><ds:X509Certificate>{self.cert_b64}</ds:X509Certificate></ds:X509Data></ds:KeyInfo></md:KeyDescriptor>
    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{self.slo_url}"/>
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{self.sso_url}"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>"""

    def resposta(
        self,
        *,
        sp_entity_id: str,
        acs: str,
        name_id: str = "ana.saml",
        in_response_to: str | None = None,
        atributos: dict[str, list[str]] | None = None,
        deslocamento_s: int = 0,
        validade_s: int = 300,
        assinar_assercao: bool = True,
        assinar_resposta: bool = True,
        chave_pem: str | None = None,
        cert_b64: str | None = None,
        id_assercao: str | None = None,
        cifrar_para_cert_b64: str | None = None,
        session_index: str | None = None,
    ) -> str:
        """SAMLResponse (base64) com uma Assertion. `deslocamento_s` desloca IssueInstant/NotBefore/NotOnOrAfter
        (10 min à frente = relógio adiantado). Chave/cert alternativos simulam "assinatura de outra chave"."""
        chave_pem = chave_pem or self.chave_pem
        cert_b64 = cert_b64 or self.cert_b64
        agora = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=deslocamento_s)
        id_resp, id_asr = "_" + secrets.token_hex(16), id_assercao or ("_" + secrets.token_hex(16))
        session_index = session_index or ("_" + secrets.token_hex(8))
        irt = f' InResponseTo="{in_response_to}"' if in_response_to else ""
        atrs = "".join(
            f'<saml:Attribute Name="{n}" NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:basic">'
            + "".join(f'<saml:AttributeValue xsi:type="xs:string">{v}</saml:AttributeValue>' for v in vs)
            + "</saml:Attribute>"
            for n, vs in (atributos or {}).items()
        )
        assercao = f"""<saml:Assertion xmlns:saml="{NS_SAML}" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ID="{id_asr}" Version="2.0" IssueInstant="{_iso(agora)}">
  <saml:Issuer>{self.entity_id}</saml:Issuer>
  <saml:Subject>
    <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">{name_id}</saml:NameID>
    <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData NotOnOrAfter="{_iso(agora + dt.timedelta(seconds=validade_s))}" Recipient="{acs}"{irt}/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{_iso(agora - dt.timedelta(seconds=60))}" NotOnOrAfter="{_iso(agora + dt.timedelta(seconds=validade_s))}">
    <saml:AudienceRestriction><saml:Audience>{sp_entity_id}</saml:Audience></saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{_iso(agora)}" SessionIndex="{session_index}">
    <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef></saml:AuthnContext>
  </saml:AuthnStatement>
  {"<saml:AttributeStatement>" + atrs + "</saml:AttributeStatement>" if atrs else ""}
</saml:Assertion>"""
        if assinar_assercao:
            assercao = OneLogin_Saml2_Utils.add_sign(assercao, chave_pem, _pem(cert_b64))
            if isinstance(assercao, bytes):
                assercao = assercao.decode("utf-8")
        if cifrar_para_cert_b64:
            assercao = _cifrar_assercao(assercao, cifrar_para_cert_b64)
        resposta = f"""<samlp:Response xmlns:samlp="{NS_SAMLP}" xmlns:saml="{NS_SAML}" ID="{id_resp}" Version="2.0" IssueInstant="{_iso(agora)}" Destination="{acs}"{irt}>
  <saml:Issuer>{self.entity_id}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  {assercao}
</samlp:Response>"""
        if assinar_resposta:
            resposta = OneLogin_Saml2_Utils.add_sign(resposta, chave_pem, _pem(cert_b64))
            if isinstance(resposta, bytes):
                resposta = resposta.decode("utf-8")
        return base64.b64encode(resposta.encode("utf-8")).decode("ascii")


def _cifrar_assercao(assercao_xml: str, cert_b64: str) -> str:
    """<saml:EncryptedAssertion> com xmlsec: AES-256-CBC para o conteúdo, chave de sessão cifrada por RSA-OAEP
    com o certificado do SP (é o que um IdP faz quando `assertion encryption` está ligado)."""
    doc = etree.fromstring(
        f'<saml:EncryptedAssertion xmlns:saml="{NS_SAML}">{assercao_xml}</saml:EncryptedAssertion>'.encode()
    )
    alvo = doc.find(f"{{{NS_SAML}}}Assertion")
    enc_data = xmlsec.template.encrypted_data_create(
        doc, xmlsec.constants.TransformAes256Cbc, type=xmlsec.constants.TypeEncElement, ns="xenc"
    )
    xmlsec.template.encrypted_data_ensure_cipher_value(enc_data)
    key_info = xmlsec.template.encrypted_data_ensure_key_info(enc_data, ns="dsig")
    enc_key = xmlsec.template.add_encrypted_key(key_info, xmlsec.constants.TransformRsaOaep)
    xmlsec.template.encrypted_data_ensure_cipher_value(enc_key)
    manager = xmlsec.KeysManager()
    chave = xmlsec.Key.from_memory(_pem(cert_b64).encode(), xmlsec.constants.KeyDataFormatCertPem)
    manager.add_key(chave)
    ctx = xmlsec.EncryptionContext(manager)
    ctx.key = xmlsec.Key.generate(xmlsec.constants.KeyDataAes, 256, xmlsec.constants.KeyDataTypeSession)
    cifrado = ctx.encrypt_xml(enc_data, alvo)
    doc.append(cifrado) if cifrado.getparent() is None else None
    return etree.tostring(doc, encoding="unicode")


def duplicar_assercao(saml_response_b64: str) -> str:
    """XML Signature Wrapping clássico: a asserção assinada é copiada com outro NameID e colocada antes da original
    (a assinatura continua válida para a cópia original; um validador ingênuo lê a primeira)."""
    raiz = etree.fromstring(base64.b64decode(saml_response_b64))
    original = raiz.find(f"{{{NS_SAML}}}Assertion")
    copia = etree.fromstring(etree.tostring(original))
    copia.set("ID", "_" + secrets.token_hex(16))
    nid = copia.find(f"{{{NS_SAML}}}Subject/{{{NS_SAML}}}NameID")
    nid.text = "admin"
    for s in copia.findall("{http://www.w3.org/2000/09/xmldsig#}Signature"):
        copia.remove(s)
    original.addprevious(copia)
    return base64.b64encode(etree.tostring(raiz)).decode("ascii")


def comentario_no_nameid(saml_response_b64: str) -> str:
    """Comentário XML dentro do NameID (ataque de 2018 contra parsers que truncam o texto no comentário)."""
    xml = base64.b64decode(saml_response_b64).decode("utf-8")
    xml = xml.replace(
        '<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">ana.saml',
        '<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">admin<!---->.saml',
    )
    return base64.b64encode(xml.encode("utf-8")).decode("ascii")
