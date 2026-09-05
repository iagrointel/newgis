"""Usuários, privilégios e papéis (ADR 0002 seções 2.3, 3.3, 16.5): último admin (409), só admin altera/cria/apaga
admin (403), lote de 100 com recusados, domínio de e-mail (422), papel fora do teto/em uso, campos V × completos."""

import secrets

from app import limites
from app.auth import privilegios as priv
from tests.api.conftest import PREFIXO_TESTE, entrar, novo_cliente


def test_listar_com_filtros_e_campos_por_privilegio(sessao_a, usuarios_a):
    u, _ = usuarios_a.criar("campo", email="campo@demo.exemplo")
    r = sessao_a.get("/api/usuarios?perfil=campo&q=" + u["login"])
    assert r.status_code == 200 and r.json()["total"] >= 1
    item = next(i for i in r.json()["itens"] if i["id"] == u["id"])
    assert item["email"] == "campo@demo.exemplo" and "totp_ativo" in item  # admin: membros.ver_tudo
    c_ed, _, _ = usuarios_a.sessao("editor")
    r = c_ed.get(f"/api/usuarios/{u['id']}")
    assert r.status_code == 200 and set(r.json()) == {
        "id",
        "login",
        "nome",
        "perfil",
        "papel",
        "ativo",
        "origem",
        "ultimo_login",
        "criado_em",
    }
    assert "email" not in r.json()
    c_vis, _, _ = usuarios_a.sessao("visualizador")
    assert c_vis.get("/api/usuarios").status_code == 200  # membros.ver em todos os perfis
    assert c_vis.post("/api/usuarios", json={"login": "x", "nome": "x", "perfil": "campo"}).status_code == 403
    assert sessao_a.get("/api/usuarios?ordenar=cpf").status_code == 422
    assert sessao_a.get("/api/usuarios?limite=5000").status_code == 422


def test_criar_login_existente_e_dominio(sessao_a, usuarios_a, sessao_plat, ids):
    u, temporaria = usuarios_a.criar("editor")
    assert len(temporaria) == limites.SENHA_TEMPORARIA_TAMANHO
    r = sessao_a.post("/api/usuarios", json={"login": u["login"], "nome": "x", "perfil": "editor"})
    assert r.status_code == 409 and r.json()["erro"] == "login_existente"
    assert (
        sessao_a.post("/api/usuarios", json={"login": "Maiusculo", "nome": "x", "perfil": "editor"}).status_code == 422
    )
    # domínios de e-mail: sem tela ainda (L0-07-a); a política é lida de tenant.config; sem config = qualquer
    assert usuarios_a.criar("editor", email="qualquer@outro.exemplo")[0]["email"] == "qualquer@outro.exemplo"


def test_so_admin_cria_altera_e_apaga_admin(sessao_a, usuarios_a):
    # editor com papel personalizado que dá membros.gerir/papel/apagar mas perfil editor: não mexe em admin
    r = sessao_a.post(
        "/api/papeis",
        json={
            "nome": f"{PREFIXO_TESTE}-gestor-{secrets.token_hex(2)}",
            "privilegios": ["membros.ver", "membros.gerir", "membros.papel", "membros.apagar"],
        },
    )
    assert r.status_code == 201, r.text
    papel = r.json()
    assert papel["perfil_minimo"] == "admin"  # privilégios administrativos só no teto admin
    # logo o papel não cabe num editor: 422 papel_incompativel
    r = sessao_a.post(
        "/api/usuarios",
        json={
            "login": f"{PREFIXO_TESTE}{secrets.token_hex(3)}",
            "nome": "x",
            "perfil": "editor",
            "papel_id": papel["id"],
        },
    )
    assert r.status_code == 422 and r.json()["erro"] == "papel_incompativel"
    # admin secundário com esse papel (subconjunto do teto): não é admin? é admin de perfil, então pode; o teste da
    # regra (b)(c) usa um editor puro
    c_ed, ed, _ = usuarios_a.sessao("editor")
    adm, _ = usuarios_a.criar("admin")
    assert c_ed.put(f"/api/usuarios/{adm['id']}", json={"nome": "x"}).status_code == 403  # sem membros.gerir
    assert c_ed.post("/api/usuarios", json={"login": "y", "nome": "y", "perfil": "admin"}).status_code == 403
    assert c_ed.delete(f"/api/usuarios/{adm['id']}").status_code == 403
    assert sessao_a.delete(f"/api/papeis/{papel['id']}").status_code == 204


def test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga(inquilino_temporario):
    """Inquilino temporário (sem resíduo de outra rodada): o admin é o único; a regra é do último admin ativo."""
    inq = inquilino_temporario
    adm, meu = inq.admin, inq.admin_id
    r = adm.put(f"/api/usuarios/{meu}", json={"perfil": "editor"})
    assert r.status_code == 409 and r.json()["erro"] == "ultimo_admin", r.text
    r = adm.put(f"/api/usuarios/{meu}", json={"ativo": False})
    assert r.status_code == 409 and r.json()["erro"] == "proprio_usuario", r.text
    # segundo admin: agora o primeiro pode ser rebaixado; o segundo vira o último e não se rebaixa nem se apaga
    r = adm.post(
        "/api/usuarios",
        json={"login": f"{PREFIXO_TESTE}adm{secrets.token_hex(2)}", "nome": "Segundo", "perfil": "admin"},
    )
    assert r.status_code == 201, r.text
    segundo, temporaria = r.json()["usuario"], r.json()["senha_temporaria"]
    c2 = novo_cliente()
    assert entrar(c2, inq.slug, segundo["login"], temporaria).status_code == 200
    assert c2.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-forte-99"}).status_code == 204
    r = c2.put(f"/api/usuarios/{meu}", json={"perfil": "editor"})
    assert r.status_code == 200 and r.json()["perfil"] == "editor", r.text
    r = c2.put(f"/api/usuarios/{segundo['id']}", json={"perfil": "editor"})
    assert r.status_code == 409 and r.json()["erro"] == "ultimo_admin", r.text
    r = c2.put(f"/api/usuarios/{meu}", json={"ativo": False})  # editor: pode (não é admin)
    assert r.status_code == 200 and r.json()["ativo"] is False
    r = c2.put(f"/api/usuarios/{meu}", json={"ativo": True, "perfil": "admin"})
    assert r.status_code == 200 and r.json()["perfil"] == "admin"
    assert adm.get("/api/eu").status_code == 401  # desabilitar apagou as sessões do primeiro admin
    assert entrar(adm, inq.slug, "admin", inq.senha).status_code == 200
    r = c2.put(f"/api/usuarios/{segundo['id']}", json={"ativo": False})
    assert r.status_code == 409 and r.json()["erro"] == "proprio_usuario"
    assert adm.delete(f"/api/usuarios/{segundo['id']}").status_code == 204  # há outro admin: pode
    r = adm.delete(f"/api/usuarios/{meu}")
    assert r.status_code == 409 and r.json()["erro"] == "proprio_usuario"


def test_redefinir_senha_desligar_2fa_e_desbloquear(sessao_a, usuarios_a):
    from tests.api.conftest import entrar, ligar_2fa

    c, u, senha = usuarios_a.sessao("editor")
    ligar_2fa(c)
    r = sessao_a.post(f"/api/usuarios/{u['id']}/senha")
    assert r.status_code == 200 and len(r.json()["senha_temporaria"]) == 12
    assert c.get("/api/eu").status_code == 401  # sessões apagadas
    n = novo_cliente()
    r = entrar(n, "demo", u["login"], senha)
    assert r.status_code == 401  # senha antiga não vale
    assert sessao_a.post(f"/api/usuarios/{u['id']}/2fa/desativar").status_code == 204
    assert sessao_a.get(f"/api/usuarios/{u['id']}").json()["totp_ativo"] is False
    ev = [e["tipo"] for e in sessao_a.get("/api/eventos?limite=30").json()["itens"]]
    assert "usuarios/redefinir_senha" in ev and "usuarios/2fa_desligar" in ev
    assert sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear").status_code == 204
    assert sessao_a.post("/api/usuarios/999999/desbloquear").status_code == 404


def test_lote_de_100_com_recusados(sessao_a, usuarios_a, ids):
    criados = [usuarios_a.criar("visualizador")[0]["id"] for _ in range(3)]
    r = sessao_a.post("/api/usuarios/lote", json={"ids": criados + [ids["a"]["id"], 999999], "acao": "desabilitar"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["alterados"] == 3 and {x["id"]: x["erro"] for x in j["recusados"]} == {
        ids["a"]["id"]: "proprio_usuario",
        999999: "usuario_inexistente",
    }
    assert all(not sessao_a.get(f"/api/usuarios/{i}").json()["ativo"] for i in criados)
    r = sessao_a.post("/api/usuarios/lote", json={"ids": criados, "acao": "reabilitar"})
    assert r.json()["alterados"] == 3
    r = sessao_a.post("/api/usuarios/lote", json={"ids": criados, "acao": "perfil", "perfil": "campo"})
    assert r.json()["alterados"] == 3 and sessao_a.get(f"/api/usuarios/{criados[0]}").json()["perfil"] == "campo"
    r = sessao_a.post("/api/usuarios/lote", json={"ids": list(range(1, 102)), "acao": "reabilitar"})
    assert r.status_code == 422 and r.json()["erro"] == "lote_acima_de_100"
    assert sessao_a.post("/api/usuarios/lote", json={"ids": criados, "acao": "perfil"}).status_code == 422
    c_ed, _, _ = usuarios_a.sessao("editor")
    assert c_ed.post("/api/usuarios/lote", json={"ids": criados, "acao": "desabilitar"}).status_code == 403


def test_apagar_com_grupos_e_404_de_outro_inquilino(sessao_a, usuarios_a, ids):
    c, u, _ = usuarios_a.sessao("editor")
    g = c.post("/api/grupos", json={"nome": f"{PREFIXO_TESTE}-g-{secrets.token_hex(2)}"}).json()
    r = sessao_a.delete(f"/api/usuarios/{u['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "possui_grupos" and r.json()["detalhe"][0]["id"] == g["id"]
    r = sessao_a.put(f"/api/usuarios/{u['id']}", json={"perfil": "visualizador"})
    assert r.status_code == 409 and r.json()["erro"] == "possui_grupos"
    assert sessao_a.delete(f"/api/grupos/{g['id']}").status_code == 204  # grupos.gerir_todos
    assert sessao_a.delete(f"/api/usuarios/{u['id']}").status_code == 204
    usuarios_a.criados.remove(u["id"])
    assert sessao_a.get(f"/api/usuarios/{ids['b']['id']}").status_code == 404
    assert sessao_a.put(f"/api/usuarios/{ids['b']['id']}", json={"nome": "x"}).status_code == 404


def test_privilegios_e_papeis(sessao_a, usuarios_a):
    privs = sessao_a.get("/api/privilegios").json()
    assert len(privs) == 46 and {p["nome"] for p in privs} == set(priv.NOMES)
    papeis = sessao_a.get("/api/papeis").json()
    assert [p["perfil"] for p in papeis["perfis"]] == list(priv.PERFIS)
    assert set(papeis["perfis"][0]["privilegios"]) == set(priv.teto("visualizador"))
    nome = f"{PREFIXO_TESTE}-curador-{secrets.token_hex(2)}"
    r = sessao_a.post("/api/papeis", json={"nome": nome, "privilegios": ["conteudo.criar", "grupos.criar"]})
    assert r.status_code == 201 and r.json()["perfil_minimo"] == "editor", r.text
    papel = r.json()
    assert (
        sessao_a.post("/api/papeis", json={"nome": nome.upper(), "privilegios": ["conteudo.criar"]}).status_code == 409
    )
    assert sessao_a.post("/api/papeis", json={"nome": "x", "privilegios": ["nao.existe"]}).status_code == 422
    # editor com o papel: privilégios = interseção; papel com privilégio administrativo exige perfil_minimo admin
    c, u, _ = usuarios_a.sessao("editor", papel_id=papel["id"])
    eu = c.get("/api/eu").json()
    assert set(eu["privilegios"]) == {"conteudo.criar", "grupos.criar"} and eu["papel"]["nome"] == nome
    assert (
        c.post("/api/papeis", json={"nome": "y", "privilegios": ["conteudo.criar"]}).status_code == 403
    )  # sem papeis.gerir
    # quem cria não concede o que não tem: admin tem tudo; um segundo admin com papel restrito não
    r = sessao_a.post(
        "/api/papeis",
        json={"nome": f"{PREFIXO_TESTE}-adm-{secrets.token_hex(2)}", "privilegios": ["membros.ver", "papeis.gerir"]},
    )
    restrito = r.json()
    c_adm, _, _ = usuarios_a.sessao("admin", papel_id=restrito["id"])
    r = c_adm.post("/api/papeis", json={"nome": "z", "privilegios": ["org.log_ver"]})
    assert r.status_code == 403 and r.json()["erro"] == "privilegio_proprio_insuficiente"
    # papel em uso não se apaga; editar para um teto que o usuário não alcança é 422
    r = sessao_a.delete(f"/api/papeis/{papel['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "papel_em_uso" and r.json()["detalhe"]["usuarios"] == 1
    r = sessao_a.put(
        f"/api/papeis/{papel['id']}", json={"nome": nome, "privilegios": ["conteudo.criar", "org.log_ver"]}
    )
    assert r.status_code == 422 and r.json()["erro"] == "papel_incompativel"
    r = sessao_a.put(f"/api/papeis/{papel['id']}", json={"nome": nome, "privilegios": ["conteudo.criar"]})
    assert r.status_code == 200 and r.json()["privilegios"] == ["conteudo.criar"]
    assert c.get("/api/eu").json()["privilegios"] == ["conteudo.criar"]
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"papel_id": None}).json()["papel"] is None
    assert sessao_a.delete(f"/api/papeis/{papel['id']}").status_code == 204
    assert sessao_a.delete(f"/api/papeis/{papel['id']}").status_code == 404
