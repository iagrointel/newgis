"""Item L6-02-i-google-sheets, unidade: formas de URL de planilha -> URL canônica de exportação CSV,
validação do JSON da conta de serviço (sem vazar segredo nas mensagens), JWT RS256 (assinatura conferida
com a chave pública correspondente) e despacho de autenticação por tipo.

A troca de token contra um servidor OAuth2 de verdade (com verificação da assinatura) está na suíte de API
(tests/api/conexao/test_google_sheets.py) — aqui não se abre socket."""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.conexao import google_sheets

PREFIXO = "https://docs.google.com"
ID = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
PAC = "2PACX-1vRZ0JxK0EXEMPLOabc123"


def conta_servico_valida() -> dict:
    """Conta de serviço gerada na hora (RSA 2048 real): o JSON tem exatamente os campos do arquivo que o
    console do Google entrega, mais um marcador de texto que nenhuma mensagem de erro pode conter."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return {
        "type": "service_account",
        "project_id": "projeto-de-teste",
        "private_key_id": "ab12cd34",
        "private_key": pem,
        "client_email": "leitor-planilhas@projeto-de-teste.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "token_uri": "https://oauth2.googleapis.com/token",
        "MARCADOR_SECRETO": "texto-que-nunca-pode-aparecer-em-erro",
    }


# --------------------------------------------------------------------- URL -> exportação CSV
@pytest.mark.parametrize("url, esperada", [
    (f"{PREFIXO}/spreadsheets/d/{ID}", f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv"),
    (f"{PREFIXO}/spreadsheets/d/{ID}/edit", f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv"),
    (f"{PREFIXO}/spreadsheets/d/{ID}/edit#gid=42", f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv&gid=42"),
    (f"{PREFIXO}/spreadsheets/d/{ID}/edit?usp=sharing&gid=7",
     f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv&gid=7"),
    (f"{PREFIXO}/spreadsheets/d/{ID}/pubhtml", f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv"),
    (f"{PREFIXO}/spreadsheets/d/{ID}/export?format=xlsx", f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv"),
    (f"{PREFIXO}/spreadsheets/d/e/{PAC}/pubhtml",
     f"{PREFIXO}/spreadsheets/d/e/{PAC}/pub?output=csv&single=true"),
    (f"{PREFIXO}/spreadsheets/d/e/{PAC}/pub?gid=99&single=true",
     f"{PREFIXO}/spreadsheets/d/e/{PAC}/pub?output=csv&single=true&gid=99"),
])
def test_formas_de_url_viram_exportacao_csv(url, esperada):
    assert google_sheets.url_exportacao_csv(url, prefixo=PREFIXO) == esperada


@pytest.mark.parametrize("url", [
    "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",  # é Docs
    "https://docs.google.com/spreadsheets/",          # sem id
    "https://docs.google.com/spreadsheets/d/curto",   # id curto demais
    "https://planilhas.evil.example/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",  # outro host
    "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view",
    "https://docs.google.com.evil.example/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
])
def test_url_que_nao_e_planilha_e_recusada(url):
    with pytest.raises(google_sheets.ErroGoogleSheets) as exc:
        google_sheets.url_exportacao_csv(url, prefixo=PREFIXO)
    assert exc.value.motivo == "url_nao_e_planilha_google"


def test_gid_invalido_nao_entra_na_url():
    """gid com letra (parâmetro injetado) é ignorado, nunca copiado para a URL de exportação."""
    saida = google_sheets.url_exportacao_csv(f"{PREFIXO}/spreadsheets/d/{ID}/edit#gid=12x3", prefixo=PREFIXO)
    assert saida == f"{PREFIXO}/spreadsheets/d/{ID}/export?format=csv"


# --------------------------------------------------------------------- JSON da conta de serviço
def test_conta_servico_valida_passa_com_chave_carregada():
    conta = google_sheets.validar_conta_servico(json.dumps(conta_servico_valida()))
    assert conta["client_email"].endswith("gserviceaccount.com")
    assert isinstance(conta["_chave_rsa"], rsa.RSAPrivateKey)


@pytest.mark.parametrize("alteracao, trecho_mensagem", [
    (lambda c: c.update(type="authorized_user"), "conta de serviço"),
    (lambda c: c.pop("client_email"), "client_email"),
    (lambda c: c.pop("private_key"), "private_key"),
    (lambda c: c.pop("token_uri"), "token_uri"),
    (lambda c: c.update(token_uri="http://oauth2.googleapis.com/token"), "https"),
    (lambda c: c.update(client_email="nao-e-email"), "client_email"),
    (lambda c: c.update(private_key="-----BEGIN PRIVATE KEY-----\nlixo\n-----END PRIVATE KEY-----\n"),
     "private_key"),
])
def test_conta_servico_invalida_nomeia_so_o_campo(alteracao, trecho_mensagem):
    conta = conta_servico_valida()
    alteracao(conta)
    bruto = json.dumps(conta)
    with pytest.raises(google_sheets.ErroGoogleSheets) as exc:
        google_sheets.validar_conta_servico(bruto)
    assert exc.value.motivo == "credencial_invalida"
    assert trecho_mensagem in exc.value.detalhe
    # cláusula do portão: a mensagem NUNCA carrega material da credencial
    assert "texto-que-nunca-pode-aparecer-em-erro" not in exc.value.detalhe
    assert "projeto-de-teste.iam.gserviceaccount.com" not in exc.value.detalhe
    assert "BEGIN" not in exc.value.detalhe


def test_credencial_que_nao_e_json():
    with pytest.raises(google_sheets.ErroGoogleSheets, match="JSON"):
        google_sheets.validar_conta_servico("isto nao e json {")


# --------------------------------------------------------------------- JWT RS256
def _desmontar(jwt: str) -> tuple[dict, dict, bytes, bytes]:
    cab, pay, ass = jwt.split(".")
    dec = lambda s: json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
    return dec(cab), dec(pay), base64.urlsafe_b64decode(ass + "=" * (-len(ass) % 4)), f"{cab}.{pay}".encode()


def test_jwt_assinado_confere_com_a_chave_publica():
    conta = google_sheets.validar_conta_servico(json.dumps(conta_servico_valida()))
    agora = int(time.time())
    jwt = google_sheets.montar_jwt(conta, agora=agora)
    cabecalho, corpo, assinatura, assinado = _desmontar(jwt)
    assert cabecalho == {"alg": "RS256", "typ": "JWT", "kid": "ab12cd34"}
    assert corpo["iss"] == conta["client_email"]
    assert corpo["scope"] == google_sheets.ESCOPO_SOMENTE_LEITURA
    assert corpo["aud"] == conta["token_uri"]
    assert corpo["exp"] - corpo["iat"] == google_sheets.TOKEN_TTL_S
    conta["_chave_rsa"].public_key().verify(assinatura, assinado, padding.PKCS1v15(), hashes.SHA256())


def test_jwt_adulterado_nao_confere():
    conta = google_sheets.validar_conta_servico(json.dumps(conta_servico_valida()))
    jwt = google_sheets.montar_jwt(conta)
    cab, pay, ass = jwt.split(".")
    corpo = json.loads(base64.urlsafe_b64decode(pay + "=" * (-len(pay) % 4)))
    corpo["scope"] = "https://www.googleapis.com/auth/spreadsheets"  # adultera o escopo DEPOIS de assinar
    pay_adulterado = base64.urlsafe_b64encode(
        json.dumps(corpo, separators=(",", ":")).encode()).rstrip(b"=").decode()
    assinatura = base64.urlsafe_b64decode(ass + "=" * (-len(ass) % 4))
    with pytest.raises(Exception):  # InvalidSignature da cryptography
        conta["_chave_rsa"].public_key().verify(
            assinatura, f"{cab}.{pay_adulterado}".encode(), padding.PKCS1v15(), hashes.SHA256())


# --------------------------------------------------------------------- despacho de autenticação
def test_despacho_tipos_antigos_preservado():
    assert google_sheets.cabecalhos_auth("http", "tok123") == {"Authorization": "Bearer tok123"}
    assert google_sheets.cabecalhos_auth("http", None) is None
    assert google_sheets.cabecalhos_auth("wfs", None) is None


def test_despacho_planilha_publica_sem_cabecalho():
    assert google_sheets.cabecalhos_auth("google_sheets", None) is None


def test_despacho_planilha_privada_com_credencial_invalida_fala_portugues():
    with pytest.raises(google_sheets.ErroGoogleSheets) as exc:
        google_sheets.cabecalhos_auth("google_sheets", "nao e json")
    assert exc.value.motivo == "credencial_invalida"
