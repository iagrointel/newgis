"""e2e /aceitar-convite (item L0-07-d-smtp-convites): o admin cria um convite pela API (inquilino demo, sem
SMTP configurado -> link_manual), o navegador (SEM sessão) abre o link, preenche login/nome/senha e cria a
conta; login com a senha escolhida confirma. Captura em tests/e2e/capturas/L0-07-d-smtp-convites_*.png."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
ITEM = "L0-07-d-smtp-convites"


def _capturar(page, nome: str):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


def test_convite_ponta_a_ponta_no_navegador(page, base_url, admin_api, credenciais_demo):
    slug, _admin_login, _senha_admin = credenciais_demo
    suf = sufixo()
    email = f"e2e-convite-{suf}@teste.exemplo"
    login = f"zte2e{suf}"
    senha = f"Senha-e2e-{suf}-1"

    r = admin_api.post("/api/convites", data={"email": email, "perfil": "visualizador"})
    assert r.status == 201, r.text()
    convite = r.json()
    link = convite["link_manual"]
    assert link and "/aceitar-convite?token=" in link
    caminho = link.split(base_url, 1)[-1] if link.startswith(base_url) else link[link.index("/aceitar-convite"):]

    tela = Tela(page, base_url)
    tela.ir(caminho)
    page.wait_for_selector("#form-aceitar:not([hidden])", timeout=15000)
    assert page.inner_text("#convite-email").strip() == email
    _capturar(page, "resolvido")

    page.fill("#login", login)
    page.fill("#nome", "Convidado E2E")
    page.fill("#senha", senha)
    page.click("#aceitar")
    page.wait_for_selector("#concluido:not([hidden])", timeout=15000)
    _capturar(page, "concluido")

    tela.verificar()

    # a conta existe e entra com a senha escolhida (prova que o e2e criou de verdade, não só mudou de tela)
    r = admin_api.get(f"/api/usuarios?q={login}")
    assert r.status == 200
    itens = r.json()["itens"]
    assert any(u["login"] == login for u in itens), itens
    criado = next(u for u in itens if u["login"] == login)

    tela2 = Tela(page, base_url)
    tela2.entrar(slug, login, senha)
    tela2.verificar()

    # link usado de novo = 410 (portão do item), verificado também pelo navegador
    r2 = page.request.post(f"{base_url}/api/convites/aceitar",
                           data={"token": link.split("token=", 1)[-1], "login": f"outro{suf}",
                                 "nome": "x", "senha": senha})
    assert r2.status == 410

    admin_api.delete(f"/api/usuarios/{criado['id']}")
