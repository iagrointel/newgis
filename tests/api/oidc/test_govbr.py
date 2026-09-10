"""Item L0-08-c-govbr: adaptador gov.br contra um IdP sintético com o formato documentado (tests/govbr_fixture):
nível da conta (bronze/prata/ouro) e selos viram valores do mapeamento e decidem o perfil (regras do L0-08-e); sem
`reliability_info` no id_token, o adaptador consulta a API de confiabilidades com o access_token; o CPF nunca
aparece em login, sujeito externo, evento ou log; refutação: id_token com nível 'gold' assinado por OUTRO issuer é
401 e nunca cria sessão. Não precisa de Docker (servidor em thread); o teste real com credencial do órgão fica
pendente em docs/PARIDADE.md."""

import re

import httpx
import pytest

from app.auth import govbr
from tests.api.conftest import novo_cliente
from tests.govbr_fixture.idp_falso import IdpGovBrFalso

ITEM = "L0-08-c-govbr"
CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


@pytest.fixture(scope="module")
def idp():
    servidor = IdpGovBrFalso().iniciar()
    yield servidor
    servidor.parar()


@pytest.fixture(scope="module")
def provedor(idp, sessao_a):
    corpo = {
        "habilitado": True, "rotulo": "Entrar com gov.br (teste)", "ordem": 2, "issuer": idp.issuer,
        "client_id": "cliente-govbr-teste", "client_secret": "segredo-de-teste-govbr",
        "escopos": govbr.ESCOPOS_PADRAO, "atributo_grupos": "groups", "perfil_padrao": None,
        "mapa_grupo_perfil": {}, "modelo": "govbr", "api_base": idp.issuer,
    }
    r = sessao_a.post("/api/org/oidc", json=corpo)
    assert r.status_code == 201, r.text
    criado = r.json()
    assert criado["modelo"] == "govbr" and criado["api_base"] == idp.issuer
    regras = {
        "criacao": "automatica",
        "padrao": {"papel_id": None, "grupos": []},
        "mapa": {
            "nivel:ouro": {"perfil": "admin"},
            "nivel:prata": {"perfil": "editor"},
            "selo:401": {"perfil": "visualizador"},  # biometria facial Senatran (prata) = leitura
        },
    }
    r = sessao_a.put(f"/api/org/logins/oidc/{criado['id']}", json={"provisionamento": regras})
    assert r.status_code == 200, r.text
    yield {**criado, "corpo": corpo}
    for u in sessao_a.get("/api/usuarios?limite=1000").json().get("itens", []):
        if u["origem"] == "oidc" and (u["login"] in ("ouro", "prata", "bronze") or u["login"].startswith("govbr-")):
            sessao_a.delete(f"/api/usuarios/{u['id']}")
    sessao_a.delete(f"/api/org/oidc/{criado['id']}")


def _login(cliente, idp, cpf: str, provedor_id: int):
    idp.cidadao_atual = cpf
    r = cliente.get(f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_id}", follow_redirects=False)
    assert r.status_code == 302, r.text
    r_idp = httpx.get(r.headers["location"], follow_redirects=False, timeout=10)
    assert r_idp.status_code == 302, r_idp.text
    qs = httpx.URL(r_idp.headers["location"]).params
    return cliente.get("/api/sso/oidc/retorno", params={"code": qs["code"], "state": qs["state"]})


def test_nivel_ouro_vira_admin_e_selos_amr_entram_no_mapeamento(idp, sessao_a, provedor, medida):
    c = novo_cliente()
    r = _login(c, idp, "11111111111", provedor["id"])
    assert r.status_code == 200, r.text
    eu = c.get("/api/eu").json()
    assert eu["perfil"] == "admin" and eu["origem"] == "oidc" and eu["login"] == "ouro"
    # o CPF nunca aparece: login, sujeito externo (pseudônimo), eventos
    u = next(x for x in sessao_a.get("/api/usuarios?q=ouro&limite=50").json()["itens"] if x["login"] == "ouro")
    detalhe = sessao_a.get(f"/api/usuarios/{u['id']}").json()
    assert "11111111111" not in str(detalhe) and not CPF.search(str(detalhe))
    eventos = sessao_a.get("/api/eventos?limite=30").json()["itens"]
    assert not any("11111111111" in str(e) for e in eventos)
    assert idp.chamadas_api == []  # nível veio do id_token: a API não foi chamada
    medida(ITEM)("nivel_ouro_vira_admin", 1, "caso",
                 "tests/api/oidc/test_govbr.py: IdP sintético com o formato do roteiro")


def test_nivel_prata_vira_editor_e_bronze_sem_regra_nao_entra(idp, provedor):
    c = novo_cliente()
    assert _login(c, idp, "22222222222", provedor["id"]).status_code == 200
    assert c.get("/api/eu").json()["perfil"] == "editor"
    c2 = novo_cliente()
    r = _login(c2, idp, "33333333333", provedor["id"])
    assert r.status_code == 403 and r.json()["erro"] == "sem_grupo_mapeado", r.text  # sem perfil padrão
    assert c2.get("/api/eu").status_code == 401


def test_sem_reliability_no_id_token_consulta_a_api_de_confiabilidades(idp, provedor):
    idp.chamadas_api.clear()
    c = novo_cliente()
    r = _login(c, idp, "44444444444", provedor["id"])
    assert r.status_code == 200, r.text
    eu = c.get("/api/eu").json()
    assert eu["perfil"] == "editor"  # prata pela API
    assert eu["login"].startswith("govbr-") and "44444444444" not in eu["login"]  # sem e-mail: login pelo pseudônimo
    assert any(p.endswith("/niveis") for p in idp.chamadas_api)
    assert any(p.endswith("/confiabilidades") for p in idp.chamadas_api)


def test_refutacao_id_token_de_outro_issuer_com_nivel_ouro_e_401(idp, provedor, sessao_a):
    idp.forjar_outro_issuer = True
    try:
        c = novo_cliente()
        r = _login(c, idp, "33333333333", provedor["id"])
        assert r.status_code == 401 and r.json()["erro"] == "token_invalido", r.text
        assert c.get("/api/eu").status_code == 401
        assert not any(u["login"] == "bronze" for u in sessao_a.get("/api/usuarios?q=bronze&limite=50").json()["itens"])
    finally:
        idp.forjar_outro_issuer = False


def test_configuracao_do_provedor_govbr(sessao_a, provedor, idp):
    lista = sessao_a.get("/api/org/logins").json()
    assert lista["redirect_uri_oidc"].endswith("/api/sso/oidc/retorno")
    assert lista["govbr"]["issuer_producao"] == "https://sso.acesso.gov.br"
    assert lista["govbr"]["escopos"] == govbr.ESCOPOS_PADRAO
    p = next(x for x in lista["provedores"] if x["tipo"] == "oidc" and x["id"] == provedor["id"])
    assert p["provisionamento"]["mapa"]["nivel:ouro"]["perfil"] == "admin"
    # api_base deduzida do issuer oficial quando ausente; modelo inválido = 422; api_base http fora de loopback = 422
    corpo = {**provedor["corpo"], "issuer": govbr.ISSUER_STAGING, "api_base": None}
    r = sessao_a.put(f"/api/org/oidc/{provedor['id']}", json=corpo)
    assert r.status_code == 200 and r.json()["api_base"] == govbr.API_STAGING, r.text
    invalido = {**provedor["corpo"], "modelo": "outro"}
    assert sessao_a.put(f"/api/org/oidc/{provedor['id']}", json=invalido).status_code == 422
    r = sessao_a.put(f"/api/org/oidc/{provedor['id']}", json={**provedor["corpo"], "api_base": "http://api.exemplo.gov.br"})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "api_base"
    assert sessao_a.put(f"/api/org/oidc/{provedor['id']}", json=provedor["corpo"]).status_code == 200


def test_unidade_valores_do_adaptador():
    claims = {"sub": "12345678901", "reliability_info": {"level": "silver", "reliabilities": [{"id": "602"}]},
              "amr": ["passwd", "mfa"]}
    assert govbr.valores_do_id_token(claims) == ["nivel:prata", "selo:602", "amr:passwd", "amr:mfa"]
    assert govbr.nivel_de_texto("3 (Ouro)") == "ouro" and govbr.nivel_de_texto("gold") == "ouro"
    assert govbr.nivel_de_texto("2") == "prata" and govbr.nivel_de_texto("x") is None
    assert govbr.pseudonimo("123.456.789-01") == govbr.pseudonimo("12345678901") and len(govbr.pseudonimo("1")) == 64
    assert govbr.login_de({"email": "Ana.Silva@x.gov.br"}, "abc") == "ana.silva"
    assert govbr.login_de({}, "0123456789abcdef") == "govbr-0123456789ab"
    assert govbr.valores_de({"sub": "1"}, None, None) == []
