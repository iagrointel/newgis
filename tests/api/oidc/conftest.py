"""Fixtures do item L0-08-a-oidc: sobe/derruba o Keycloak de teste (`tests/oidc_fixture/`, realm
`plataforma-teste-oidc` versionado em `realm.json`) e dirige o fluxo Authorization Code + PKCE inteiro por
`httpx` puro — sem navegador (`google-chrome --headless` está quebrado nesta máquina, achado documentado na
memória da casa). Achado que exigiu tratamento especial: o Keycloak marca `AUTH_SESSION_ID`/`KC_RESTART`
como `Secure` mesmo servindo em `http://` puro em modo dev; o *cookie jar* automático do `httpx.Client`
descarta cookie `Secure` sobre conexão não cifrada, por isso os `Set-Cookie` são copiados manualmente para
um cabeçalho `Cookie` explícito no POST seguinte (função `_completar_login_no_idp` abaixo).

Todos os testes deste diretório são `lento` (contêiner Docker; ver `pyproject.toml`), marcados no módulo de
teste, não aqui."""

import base64
import hashlib
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

DIR = Path(__file__).resolve().parents[2] / "oidc_fixture"
HOST, PORTA = "127.0.0.1", 8236
ISSUER = f"http://{HOST}:{PORTA}/realms/plataforma-teste-oidc"
CLIENT_ID = "plat-teste"
CLIENT_ID_OUTRO = "plat-teste-outro"  # aud de outro cliente — usado pela refutação (audiência trocada)
MAPA_GRUPO_PERFIL = {"gg-oidc-admin": "admin", "gg-oidc-leitura": "visualizador"}
USUARIOS = {  # username: senha (tests/oidc_fixture/realm.json tem as credenciais)
    "ana.oidc": "Teste-oidc-1",  # grupo gg-oidc-admin
    "bruno.oidc": "Teste-oidc-2",  # grupo gg-oidc-leitura
    "carla.oidc": "Teste-oidc-3",  # sem grupo (teste de 'sem_grupo_mapeado')
}


def _descoberta_pronta() -> bool:
    try:
        r = httpx.get(ISSUER + "/.well-known/openid-configuration", timeout=1)
        return r.status_code == 200 and r.json().get("issuer") == ISSUER
    except Exception:  # noqa: BLE001 — qualquer falha aqui só significa "ainda não"
        return False


@pytest.fixture(scope="session")
def servidor_oidc():
    """Sobe o contêiner Keycloak (`tests/oidc_fixture/subir.sh`); pula a suíte quando Docker não está
    disponível nesta máquina (nunca falha o resto do `make check` por isso)."""
    if shutil.which("docker") is None:
        pytest.skip("docker ausente nesta máquina; sem docker, mock do protocolo seria a alternativa (não construída)")
    subprocess.run(["bash", str(DIR / "subir.sh")], check=True, capture_output=True, text=True, timeout=120)
    limite = time.monotonic() + 15
    while not _descoberta_pronta():
        if time.monotonic() > limite:
            pytest.fail("keycloak não respondeu (descoberta OIDC do realm de teste) em 15 s")
        time.sleep(0.3)
    yield {"issuer": ISSUER}
    subprocess.run(["bash", str(DIR / "descer.sh")], check=False, capture_output=True, text=True)


def derrubar_servidor_oidc():
    """Usado pelo teste que prova 'provedor desligado não impede o login local do admin' — chamado DENTRO
    do teste (não como fixture) para poder religar em seguida sem vazar o servidor parado para outros testes."""
    subprocess.run(["bash", str(DIR / "descer.sh")], check=False, capture_output=True, text=True)


def religar_servidor_oidc():
    subprocess.run(["bash", str(DIR / "subir.sh")], check=True, capture_output=True, text=True, timeout=120)
    limite = time.monotonic() + 15
    while not _descoberta_pronta():
        if time.monotonic() > limite:
            pytest.fail("keycloak não religou (descoberta OIDC) em 15 s")
        time.sleep(0.3)


def gerar_pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)[:128]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verificador, desafio


def autorizar_no_idp(client_id: str, redirect_uri: str, state: str, nonce: str, code_challenge: str) -> httpx.Client:
    """Abre a sessão de navegação (cliente httpx com cookies) na tela de login do IdP; devolve o cliente já
    posicionado no formulário de login (chamador ainda decide login/senha)."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    c = httpx.Client(timeout=10)
    r = c.get(f"{ISSUER}/protocol/openid-connect/auth?" + urlencode(params), follow_redirects=True)
    c._pagina_login = r  # guardado para _completar_login_no_idp ler o formulário
    return c


def _cookies_da_resposta(c: httpx.Client, r: httpx.Response) -> str:
    cookies: dict[str, str] = {}
    for resp in list(r.history) + [r]:
        for raw in resp.headers.get_list("set-cookie"):
            nome, _, resto = raw.partition("=")
            cookies[nome.strip()] = resto.split(";", 1)[0]
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def completar_login_no_idp(c: httpx.Client, username: str, senha: str) -> dict[str, list[str]]:
    """POST usuário/senha no formulário de login capturado por `autorizar_no_idp`; devolve os parâmetros da
    query string do redirect final (contém `code`+`state`, ou `error` quando o IdP recusa)."""
    r = c._pagina_login
    m = re.search(r'<form[^>]+action="([^"]+)"', r.text)
    assert m, f"formulário de login não encontrado (Keycloak mudou o HTML?): {r.text[:300]}"
    acao = m.group(1).replace("&amp;", "&")
    cabecalho_cookie = _cookies_da_resposta(c, r)
    r2 = c.post(
        acao,
        data={"username": username, "password": senha},
        headers={"Cookie": cabecalho_cookie},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303), f"login no IdP falhou (status {r2.status_code}): {r2.text[:300]}"
    local = r2.headers["location"]
    return parse_qs(urlsplit(local).query)
