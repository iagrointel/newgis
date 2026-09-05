"""e2e i18n: nenhum texto visível das telas do L0-02 pode ser uma chave crua do dicionário (ADR 0001 seção 11 +
L5 D16). Percorre as telas logado, mais /conta com pendência de senha (usuário novo) e /entrar; um token do
innerText que case ^[a-z]+\\.[a-z_.]+$ e seja chave de web/js/i18n/pt-BR.json, ou tenha prefixo de um espaço de
nomes do dicionário sem ser nome de privilégio, reprova. Nomes de privilégio (membros.ver) têm a mesma forma e
são dado, por isso são excluídos pela lista viva de GET /api/privilegios."""

import json
import re

import pytest

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CHAVE = re.compile(r"^[a-z0-9]+\.[a-z0-9_.]+$")
TELAS = ["/", "/conta", "/admin/usuarios", "/admin/grupos", "/admin/papeis", "/admin/tokens", "/admin/log"]


def _dicionario() -> dict:
    return json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))


def _cruas(texto: str, chaves: set[str], espacos: set[str], privilegios: set[str]) -> list[str]:
    achadas = []
    for token in re.split(r"[\s,;:()\[\]{}\"']+", texto):
        if not CHAVE.match(token) or token in privilegios:
            continue
        if token in chaves or token.split(".")[0] in espacos:
            achadas.append(token)
    return sorted(set(achadas))


def _texto(page) -> str:
    return page.evaluate("() => document.body.innerText")


def test_nenhuma_chave_crua_nas_telas(page, base_url, credenciais_demo, admin_api):
    slug, admin_login, senha_admin = credenciais_demo
    dic = _dicionario()
    chaves = set(dic)
    espacos = {k.split(".")[0] for k in dic}
    tela = Tela(page, base_url)
    # /entrar sem sessão (mais o estado de erro, que também traduz)
    tela.esperar_status(401)
    tela.ir(f"/entrar?inquilino={slug}")
    page.fill("#login", admin_login)
    page.fill("#senha", "senha-errada-1")
    page.click("#entrar")
    page.wait_for_selector("#aviso:not([hidden])", timeout=15000)
    problemas = {"/entrar": _cruas(_texto(page), chaves, espacos, set())}
    tela.entrar(slug, admin_login, senha_admin)
    r = tela.api("GET", "/api/privilegios")
    privilegios = {p["nome"] for p in r.json()} if r.status == 200 else set()
    for caminho in TELAS:
        if page.request.get(f"{base_url}{caminho}").status == 404:
            problemas[caminho] = ["(rota 404 no backend; não conferida)"]
            continue
        tela.ir(caminho)
        problemas[caminho] = _cruas(_texto(page), chaves, espacos, privilegios)
    # /conta com pendência de senha (usuário novo): é onde a seção de sessões mostra o texto de pendência
    login = f"e2e_i18n_{sufixo()}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "I18n E2E", "perfil": "visualizador"})
    assert r.status == 201, r.text()
    uid, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
    try:
        tela.sair()
        tela.entrar(slug, login, temporaria)
        tela.ir("/conta")
        problemas["/conta#pendencia"] = _cruas(_texto(page), chaves, espacos, privilegios)
    finally:
        admin_api.delete(f"/api/usuarios/{uid}")
    ruins = {k: v for k, v in problemas.items() if v and not v[0].startswith("(")}
    assert ruins == {}, ruins
    tela.verificar()
