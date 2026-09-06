"""e2e /admin/papeis (ADR 0002 seção 3): criar papel personalizado com dois privilégios, editar acrescentando um,
apagar. Captura L0-02-tenant-auth_papeis.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_papel_criar_editar_apagar(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    nome = f"Curador E2E {sufixo()}"
    pid = None
    tela = Tela(page, base_url)
    if page.request.get(f"{base_url}/admin/papeis").status == 404:
        pytest.skip(
            "o backend não serve /admin/papeis: falta a linha '/admin/papeis': 'admin/papeis.html' em "
            "app/paginas.py PAGINAS (tela pedida pelo gerente no T2, fora da lista da seção 15 do ADR 0002)"
        )
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/papeis")
        tela.medidas["pagina_pronta_ms_papeis"] = tela.ir("/admin/papeis")
        assert page.locator("#tabela-perfis tbody tr").count() == 4
        page.click("#novo")
        p = page.locator("#painel dialog[open]")
        p.locator("input[name='nome']").fill(nome)
        p.locator("input[name='descricao']").fill("papel do e2e")
        p.locator("input[type='checkbox']:not(:checked)").nth(0)  # garante que a matriz renderizou
        p.locator("input[value='membros.ver']").check()
        p.locator("input[value='grupos.entrar']").check()
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        papeis = tela.api("GET", "/api/papeis").json()["personalizados"]
        meu = next(x for x in papeis if x["nome"] == nome)
        pid = meu["id"]
        assert set(meu["privilegios"]) == {"membros.ver", "grupos.entrar"}
        tela.capturar("papeis")
        page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Editar").click()
        p = page.locator("#painel dialog[open]")
        p.locator("input[value='conteudo.ver_inquilino']").check()
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        meu = next(x for x in tela.api("GET", "/api/papeis").json()["personalizados"] if x["id"] == pid)
        assert "conteudo.ver_inquilino" in meu["privilegios"]
        page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Apagar").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert all(x["id"] != pid for x in tela.api("GET", "/api/papeis").json()["personalizados"])
        pid = None
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        if pid:
            admin_api.delete(f"/api/papeis/{pid}")


def _sem_extras(no: dict) -> dict:
    """`GET /api/categorias` devolve `itens`/`caminho`/`nivel`/`origem` que `CategoriaNo` (PUT) não aceita."""
    return {
        "id": no["id"],
        "nome": no["nome"],
        "codigo": no["codigo"],
        "filhas": [_sem_extras(f) for f in no["filhas"]],
    }


def test_papel_curador_categoriza_mas_nao_publica(page, base_url, credenciais_demo, admin_api, medida):
    """Cenário do portão de pronto do item L0-07-b-papeis-privilegios: papel "Curador" (`conteudo.criar` +
    `conteudo.categorias`) atribuído a um usuário novo — ele consegue reescrever a árvore de categorias
    (`conteudo.categorias`) mas NÃO consegue criar/publicar uma camada vetorial (`conteudo.publicar_camada`,
    que o papel não tem). `conteudo.categorias` é administrativo (só no teto do perfil `admin`), por isso o
    usuário é criado com perfil `admin` e o papel restringe o efetivo aos dois privilégios escolhidos (ADR 0002
    seção 3.2, interseção perfil×papel). Captura L0-02-tenant-auth_papel_curador.png (convenção de nome de
    tests/e2e/apoio.py, compartilhada por todo e2e do L0-02/L0-07)."""
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    nome_papel = f"Curador E2E {s}"
    login_curador = f"e2e_curador_{s}"
    papel_id = None
    usuario_id = None
    tela = Tela(page, base_url)
    try:
        # 1) o admin de demo cria o papel Curador pela tela
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/papeis")
        tela.ir("/admin/papeis")
        page.click("#novo")
        p = page.locator("#painel dialog[open]")
        p.locator("input[name='nome']").fill(nome_papel)
        p.locator("input[name='descricao']").fill("categoriza; não publica (e2e L0-07-b)")
        p.locator("input[value='conteudo.criar']").check()
        p.locator("input[value='conteudo.categorias']").check()
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        papeis = tela.api("GET", "/api/papeis").json()["personalizados"]
        papel = next(x for x in papeis if x["nome"] == nome_papel)
        papel_id = papel["id"]
        assert set(papel["privilegios"]) == {"conteudo.criar", "conteudo.categorias"}
        assert papel["perfil_minimo"] == "admin"  # conteudo.categorias é administrativo: só cabe no teto admin
        tela.capturar("papel_curador")

        # 2) o admin cria o usuário Curador (perfil admin — teto exigido pelo papel — com o papel atribuído)
        tela.ir("/admin/usuarios")
        page.click("#novo")
        p = page.locator("#painel dialog[open]")
        p.locator("input[name='login']").fill(login_curador)
        p.locator("input[name='nome']").fill("Curador E2E")
        p.locator("select[name='perfil']").select_option("admin")
        p.locator("select[name='papel_id']").select_option(str(papel_id))
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#senha-temporaria", timeout=15000)
        temporaria = page.text_content("#senha-temporaria").strip()
        page.locator("#painel dialog[open] button", has_text="Fechar").click()
        usuarios = tela.api("GET", f"/api/usuarios?q={login_curador}").json()["itens"]
        usuario_id = next(u["id"] for u in usuarios if u["login"] == login_curador)

        # 3) troca de sessão: entra como o próprio Curador (senha temporária -> troca obrigatória -> definitiva)
        tela.sair()
        tela.entrar(slug, login_curador, temporaria, proximo="/admin/usuarios")
        senha_definitiva = f"Senha-definitiva-1{sufixo()}"
        r = tela.api("PUT", "/api/eu/senha", {"atual": temporaria, "nova": senha_definitiva})
        assert r.status == 204, r.text()
        eu = tela.api("GET", "/api/eu").json()
        assert set(eu["privilegios"]) == {"conteudo.criar", "conteudo.categorias"}, eu["privilegios"]

        # 4) categoriza: reescreve a árvore existente SEM mudar nada (prova de escrita sem efeito colateral
        # nas categorias reais do inquilino demo, que outros e2e/telas também leem)
        atual = tela.api("GET", "/api/categorias").json()["arvore"]
        r = tela.api("PUT", "/api/categorias", {"arvore": [_sem_extras(n) for n in atual]})
        assert r.status == 200, r.text()

        # 5) não publica: criar item tipo camada_vetorial exige conteudo.publicar_camada, que o papel não deu
        tela.esperar_status(403)
        r = tela.api("POST", "/api/itens", {"tipo": "camada_vetorial", "titulo": "zt-curador-nao-publica", "dados": {}})
        assert r.status == 403, r.text()
        corpo = r.json()
        assert corpo["erro"] == "sem_privilegio" and corpo["detalhe"]["exigido"] == "conteudo.publicar_camada"

        # mas continua criando conteúdo comum (conteudo.criar) — a diferença é só o TIPO publicável
        r = tela.api(
            "POST",
            "/api/itens",
            {"tipo": "mapa", "titulo": "zt-curador-mapa-comum", "dados": {"esquema_versao": 1, "corpo": {}}},
        )
        assert r.status == 201, r.text()
        item_criado = r.json()["id"]
        admin_id = admin_api.get("/api/eu").json()["id"]
        # transfere ANTES de apagar o usuário: _itens_do_dono não distingue item na lixeira de item vivo
        # (achado do adversário deste mesmo item — ver tests/api/test_privilegios_matriz.py)
        r = admin_api.post(
            "/api/itens/transferir",
            data={"ids": [item_criado], "novo_dono_id": admin_id, "simular": False},
        )
        assert r.status == 200, r.text()
        admin_api.delete(f"/api/itens/{item_criado}")
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        if usuario_id:
            admin_api.delete(f"/api/usuarios/{usuario_id}")
        if papel_id:
            admin_api.delete(f"/api/papeis/{papel_id}")
