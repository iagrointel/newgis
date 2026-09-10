"""Item L0-08-b: portão e refutação sem Docker — um IdP sintético (`tests/saml_fixture/idp_falso.py`, chave gerada
na hora) assina respostas SAML e o ACS real da aplicação (TestClient) as julga. Casos: válida cria sessão (SP-
e IdP-initiated); sem assinatura de asserção = 401; sem assinatura de resposta = 401; assinatura de outra chave
= 401; relógio 10 min à frente = 401; replay da mesma asserção = 401; XML Signature Wrapping (asserção duplicada
com outro NameID; comentário no NameID) = 401 ou identidade original; NameID fora da regra Esri = 401; asserção
cifrada aceita (e exigida quando configurado); metadado do SP válido contra o XSD do SAML; provedor desligado não
afeta o login local; isolamento A->B."""

import base64
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from onelogin.saml2.xml_utils import OneLogin_Saml2_XML
from starlette.testclient import TestClient

from app.main import app
from tests.saml_fixture.idp_falso import IdpFalso, comentario_no_nameid, duplicar_assercao

# o python3-saml exige host com ponto nas URLs do SP; o `testserver` do TestClient padrão não serve
BASE = "http://sp.teste.invalido"
ACS = f"{BASE}/api/sso/saml/acs"


def novo_cliente() -> TestClient:
    return TestClient(app, base_url=BASE)


MAPA = {"gg-saml-admin": "admin", "gg-saml-leitura": "visualizador"}


@pytest.fixture(scope="module")
def idp():
    return IdpFalso.novo("https://idp-forjado.invalido/saml")


@pytest.fixture(scope="module")
def provedor(sessao_a, idp):
    """Provedor configurado pela API (metadado por XML) no inquilino A; removido no fim junto com as contas saml."""
    r = sessao_a.post(
        "/api/org/saml",
        json={
            "rotulo": "zt saml forjado",
            "metadado_xml": idp.metadado(),
            "mapa_grupo_perfil": MAPA,
            "perfil_padrao": None,
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    yield p
    sessao_a.delete(f"/api/org/saml/{p['id']}")
    for u in sessao_a.get("/api/usuarios?limite=200").json().get("itens", []):
        if u.get("origem") == "saml":
            sessao_a.delete(f"/api/usuarios/{u['id']}")


def _entity_id(p):
    return f"{BASE}/api/sso/saml/metadata?provedor_id={p['id']}"


def _acs(cliente, resposta_b64, relay=None):
    dados = {"SAMLResponse": resposta_b64}
    if relay:
        dados["RelayState"] = relay
    return cliente.post("/api/sso/saml/acs", data=dados, follow_redirects=False)


def _resposta(idp, p, **kw):
    kw.setdefault(
        "atributos", {"email": ["ana.saml@teste.invalido"], "name": ["Ana Saml"], "groups": ["gg-saml-admin"]}
    )
    return idp.resposta(sp_entity_id=_entity_id(p), acs=ACS, **kw)


def test_metadado_do_sp_valida_contra_o_xsd(sessao_a, provedor):
    c = novo_cliente()
    r = c.get(f"/api/sso/saml/metadata?inquilino=demo&provedor_id={provedor['id']}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/samlmetadata+xml")
    xml = r.text
    assert 'AuthnRequestsSigned="true"' in xml and 'WantAssertionsSigned="true"' in xml
    assert "<ds:Signature" in xml or "Signature" in xml  # metadado assinado (signMetadata)
    # validação contra o XSD do SAML (saml-schema-metadata-2.0.xsd embarcado na biblioteca)
    assert OneLogin_Saml2_XML.validate_xml(xml, "saml-schema-metadata-2.0.xsd", False) != "invalid_xml"
    assert _entity_id(provedor) in xml


def test_idp_initiated_valida_cria_sessao_e_perfil(idp, provedor):
    c = novo_cliente()
    r = _acs(c, _resposta(idp, provedor))
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/"
    eu = c.get("/api/eu")
    assert eu.status_code == 200, eu.text
    assert eu.json()["login"] == "ana.saml" and eu.json()["perfil"] == "admin" and eu.json()["origem"] == "saml"


def test_sp_initiated_com_transacao_e_relay(idp, provedor):
    c = novo_cliente()
    r = c.get(
        f"/api/sso/saml/iniciar?inquilino=demo&provedor_id={provedor['id']}&proximo=/mapa", follow_redirects=False
    )
    assert r.status_code == 302
    destino = r.headers["location"]
    assert destino.startswith(idp.sso_url) and "SAMLRequest=" in destino and "Signature=" in destino
    q = parse_qs(urlsplit(destino).query)
    import zlib

    pedido = zlib.decompress(base64.b64decode(q["SAMLRequest"][0]), -15).decode()
    request_id = re.search(r'ID="([^"]+)"', pedido).group(1)
    r2 = _acs(
        c,
        _resposta(
            idp, provedor, in_response_to=request_id, name_id="bruno.saml", atributos={"groups": ["gg-saml-leitura"]}
        ),
        relay="/mapa",
    )
    assert r2.status_code == 303 and r2.headers["location"] == "/mapa"
    assert c.get("/api/eu").json()["perfil"] == "visualizador"
    # a mesma transação não serve duas vezes (uso único), mesmo com asserção nova
    r3 = _acs(novo_cliente(), _resposta(idp, provedor, in_response_to=request_id, name_id="bruno.saml"))
    assert r3.status_code == 401


def test_sem_assinatura_na_assercao_e_401(idp, provedor):
    r = _acs(novo_cliente(), _resposta(idp, provedor, assinar_assercao=False))
    assert r.status_code == 401 and r.json()["erro"] == "saml_invalido"


def test_sem_assinatura_na_resposta_e_401(idp, provedor):
    r = _acs(novo_cliente(), _resposta(idp, provedor, assinar_resposta=False))
    assert r.status_code == 401


def test_assinatura_de_outra_chave_e_401(idp, provedor):
    outro = IdpFalso.novo(idp.entity_id)
    r = _acs(novo_cliente(), _resposta(idp, provedor, chave_pem=outro.chave_pem, cert_b64=outro.cert_b64))
    assert r.status_code == 401


def test_relogio_dez_minutos_a_frente_e_401(idp, provedor):
    r = _acs(novo_cliente(), _resposta(idp, provedor, deslocamento_s=600))
    assert r.status_code == 401
    # dentro da folga configurada (< 5 min) passa
    r = _acs(
        novo_cliente(),
        _resposta(idp, provedor, deslocamento_s=120, name_id="carla.saml", atributos={"groups": ["gg-saml-leitura"]}),
    )
    assert r.status_code == 303


def test_replay_da_mesma_assercao_e_401(idp, provedor):
    forjada = _resposta(idp, provedor, name_id="dora.saml", atributos={"groups": ["gg-saml-leitura"]})
    assert _acs(novo_cliente(), forjada).status_code == 303
    r = _acs(novo_cliente(), forjada)
    assert r.status_code == 401 and r.json()["erro"] == "assercao_reutilizada"
    # nem com ID de asserção igual em resposta nova
    id_fixo = "_" + "a1" * 16
    _acs(
        novo_cliente(),
        _resposta(idp, provedor, name_id="dora.saml", id_assercao=id_fixo, atributos={"groups": ["gg-saml-leitura"]}),
    )
    r = _acs(
        novo_cliente(),
        _resposta(idp, provedor, name_id="dora.saml", id_assercao=id_fixo, atributos={"groups": ["gg-saml-leitura"]}),
    )
    assert r.status_code == 401


def test_xml_signature_wrapping_nunca_vira_admin(idp, provedor):
    original = _resposta(idp, provedor, name_id="eva.saml", atributos={"groups": ["gg-saml-leitura"]})
    c = novo_cliente()
    r = _acs(c, duplicar_assercao(original))
    assert r.status_code == 401 or c.get("/api/eu").json().get("login") != "admin"
    c2 = novo_cliente()
    r = _acs(c2, comentario_no_nameid(_resposta(idp, provedor, name_id="ana.saml")))
    assert r.status_code == 401 or c2.get("/api/eu").json().get("login") != "admin"


def test_nameid_fora_da_regra_esri_e_401(idp, provedor):
    r = _acs(novo_cliente(), _resposta(idp, provedor, name_id="ana saml!"))
    assert r.status_code == 401 and r.json()["erro"] == "nameid_invalido"


def test_sem_grupo_mapeado_e_403(idp, provedor):
    r = _acs(novo_cliente(), _resposta(idp, provedor, name_id="zeca.saml", atributos={"groups": ["outro"]}))
    assert r.status_code == 403 and r.json()["erro"] == "sem_grupo_mapeado"


def test_assercao_cifrada_e_aceita_e_pode_ser_exigida(sessao_a, idp, provedor):
    cifrada = _resposta(
        idp,
        provedor,
        name_id="fabio.saml",
        atributos={"groups": ["gg-saml-leitura"]},
        cifrar_para_cert_b64=provedor["sp_certificado"],
    )
    c = novo_cliente()
    r = _acs(c, cifrada)
    assert r.status_code == 303, r.text
    assert c.get("/api/eu").json()["login"] == "fabio.saml"
    # exigir cifra: asserção em claro passa a ser recusada
    corpo = {
        "rotulo": "zt saml forjado",
        "metadado_xml": idp.metadado(),
        "mapa_grupo_perfil": MAPA,
        "assercao_cifrada": True,
    }
    assert sessao_a.put(f"/api/org/saml/{provedor['id']}", json=corpo).status_code == 200
    try:
        r = _acs(
            novo_cliente(), _resposta(idp, provedor, name_id="fabio.saml", atributos={"groups": ["gg-saml-leitura"]})
        )
        assert r.status_code == 401
        r = _acs(
            novo_cliente(),
            _resposta(
                idp,
                provedor,
                name_id="fabio.saml",
                atributos={"groups": ["gg-saml-leitura"]},
                cifrar_para_cert_b64=provedor["sp_certificado"],
            ),
        )
        assert r.status_code == 303
    finally:
        corpo["assercao_cifrada"] = False
        sessao_a.put(f"/api/org/saml/{provedor['id']}", json=corpo)


def test_logout_encerra_sessao_e_propaga_ao_idp(idp, provedor):
    c = novo_cliente()
    assert (
        _acs(c, _resposta(idp, provedor, name_id="gil.saml", atributos={"groups": ["gg-saml-leitura"]})).status_code
        == 303
    )
    r = c.get("/api/sso/saml/logout", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(idp.slo_url)
    assert "SAMLRequest=" in r.headers["location"]
    assert c.get("/api/eu").status_code == 401


def test_provedor_desligado_nao_afeta_login_local(sessao_a, cred, idp, provedor):
    corpo = {
        "rotulo": "zt saml forjado",
        "metadado_xml": idp.metadado(),
        "mapa_grupo_perfil": MAPA,
        "habilitado": False,
    }
    assert sessao_a.put(f"/api/org/saml/{provedor['id']}", json=corpo).status_code == 200
    try:
        r = _acs(novo_cliente(), _resposta(idp, provedor))
        assert r.status_code == 401
        login, senha = cred["demo"]
        c = novo_cliente()
        assert c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha}).status_code == 200
        botoes = c.get("/api/login/provedores?inquilino=demo").json()["provedores"]
        assert not any(b["tipo"] == "saml" and b["id"] == provedor["id"] for b in botoes)
    finally:
        corpo["habilitado"] = True
        sessao_a.put(f"/api/org/saml/{provedor['id']}", json=corpo)
    botoes = novo_cliente().get("/api/login/provedores?inquilino=demo").json()["provedores"]
    assert any(b["tipo"] == "saml" and b["id"] == provedor["id"] for b in botoes)


def test_provedor_de_a_invisivel_para_b(sessao_b, provedor):
    assert all(p["id"] != provedor["id"] for p in sessao_b.get("/api/org/saml").json())
    assert sessao_b.delete(f"/api/org/saml/{provedor['id']}").status_code == 404
    assert novo_cliente().get(f"/api/sso/saml/metadata?inquilino=demo2&provedor_id={provedor['id']}").status_code == 404


def test_entrada_exige_uma_fonte_e_certificado_legivel(sessao_a, idp):
    r = sessao_a.post("/api/org/saml", json={"metadado_xml": idp.metadado(), "idp_entity_id": "x"})
    assert r.status_code == 422
    r = sessao_a.post(
        "/api/org/saml",
        json={
            "idp_entity_id": "https://x.invalido",
            "idp_sso_url": "https://x.invalido/sso",
            "idp_certificado": "nao-e-certificado",
        },
    )
    assert r.status_code == 422
    r = sessao_a.post("/api/org/saml", json={"metadado_url": "http://10.0.0.1/metadata"})
    assert r.status_code == 422
