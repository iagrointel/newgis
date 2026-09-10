"""Escalonamento de privilégio pela atribuição de papel (item L0-02-g-checagem-privilegio-papel-id).

O papel personalizado RESTRINGE o teto do perfil: `plat.privilegios_de` (migração 003, seção 12.10) é a
interseção entre os privilégios do perfil e os do papel. Disso vinham dois caminhos de escalonamento, porque
`POST /api/usuarios` e `PUT /api/usuarios/{id}` conferiam só se o papel CABIA no perfil do alvo, nunca se o ATOR
tinha os privilégios que estava concedendo:

1. o ator restrito por um papel atribui a outro usuário um papel mais amplo que o seu;
2. o ator restrito tira o papel (papel_id nulo) de alguém — ou de si mesmo — e devolve o teto inteiro do perfil.

As rotas de papel já barravam a criação de papel além do próprio conjunto (`privilegio_proprio_insuficiente` em
`_validar_papel`); faltava barrar a ATRIBUIÇÃO. `_nao_conceder_alem_do_proprio` fecha os dois caminhos.

Fronteira honesta sobre a redação do portão: o portão fala em "um editor". Um editor NÃO chega a esta conferência
— `membros.papel` e `membros.gerir` só existem no teto do perfil admin, então o editor toma 403 `sem_privilegio`
antes. O teste do editor está aqui (`test_editor_nao_atribui_papel_administrativo`) e passa, mas o 403 dele vem
do portão de privilégio, não da conferência nova; quem exercita a conferência nova é o ADMINISTRADOR RESTRITO,
que é o ator real do achado.
"""

import secrets

import pytest

from tests.api.conftest import InquilinoTemporario, entrar, novo_cliente

RESERVADO = "org.integracoes"  # o privilégio que sai do papel do ator nos casos de uma-diferença


def _login() -> str:
    return f"zt{secrets.token_hex(4)}"


@pytest.fixture(scope="module")
def terreno(sessao_plat):
    """Inquilino descartável: administrador pleno, administrador RESTRITO por papel, e dois alvos."""
    inq = InquilinoTemporario(sessao_plat)
    try:
        todos = sorted(p["nome"] for p in inq.admin.get("/api/privilegios").json())
        papeis = {}
        for nome, privs in (("ator", set(todos) - {RESERVADO}), ("alvo", set(todos))):
            r = inq.admin.post("/api/papeis", json={"nome": f"zt-{nome}", "privilegios": sorted(privs)})
            assert r.status_code == 201, r.text
            papeis[nome] = r.json()["id"]
        login = _login()
        r = inq.admin.post(
            "/api/usuarios",
            json={"login": login, "nome": "Administrador restrito", "perfil": "admin", "papel_id": papeis["ator"]},
        )
        assert r.status_code == 201, r.text
        ator_id, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
        ator = novo_cliente()
        assert entrar(ator, inq.slug, login, temporaria).status_code == 200
        assert ator.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-do-ator-1x"}).status_code == 204

        alvos = {}
        for nome, perfil in (("admin", "admin"), ("editor", "editor")):
            r = inq.admin.post(
                "/api/usuarios", json={"login": _login(), "nome": f"Alvo {nome}", "perfil": perfil, "papel_id": None}
            )
            assert r.status_code == 201, r.text
            alvos[nome] = r.json()["usuario"]["id"]

        editor_login = _login()
        r = inq.admin.post(
            "/api/usuarios", json={"login": editor_login, "nome": "Editor comum", "perfil": "editor", "papel_id": None}
        )
        assert r.status_code == 201, r.text
        editor = novo_cliente()
        assert entrar(editor, inq.slug, editor_login, r.json()["senha_temporaria"]).status_code == 200
        temp = r.json()["senha_temporaria"]
        assert editor.put("/api/eu/senha", json={"atual": temp, "nova": "Senha-do-editor-1x"}).status_code == 204

        yield {"inq": inq, "ator": ator, "ator_id": ator_id, "editor": editor,
               "papeis": papeis, "alvos": alvos, "todos": todos}
    finally:
        inq.apagar()


def _definir(terreno, nome, privilegios):
    r = terreno["inq"].admin.put(
        f"/api/papeis/{terreno['papeis'][nome]}", json={"nome": f"zt-{nome}", "privilegios": sorted(privilegios)}
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def papeis_no_estado_padrao(terreno):
    """Cada caso começa com ator = todos menos RESERVADO, alvo = todos."""
    _definir(terreno, "ator", set(terreno["todos"]) - {RESERVADO})
    _definir(terreno, "alvo", set(terreno["todos"]))


def _erro(resposta) -> str:
    return resposta.json().get("erro", "")


# ---------------------------------------------------------------- cláusula 1: criação
def test_ator_restrito_nao_cria_usuario_com_papel_mais_amplo(terreno):
    r = terreno["ator"].post(
        "/api/usuarios",
        json={"login": _login(), "nome": "Novo", "perfil": "admin", "papel_id": terreno["papeis"]["alvo"]},
    )
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text
    assert r.json()["detalhe"] == [RESERVADO], r.text


def test_ator_restrito_nao_cria_administrador_sem_papel(terreno):
    """papel_id nulo concede o teto inteiro do perfil — é o mesmo escalonamento por outro caminho."""
    r = terreno["ator"].post(
        "/api/usuarios", json={"login": _login(), "nome": "Novo", "perfil": "admin", "papel_id": None}
    )
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text
    assert r.json()["detalhe"] == [RESERVADO], r.text


# ---------------------------------------------------------------- cláusula 1: edição
def test_ator_restrito_nao_atribui_papel_mais_amplo_em_edicao(terreno):
    r = terreno["ator"].put(
        f"/api/usuarios/{terreno['alvos']['admin']}", json={"papel_id": terreno["papeis"]["alvo"]}
    )
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text


def test_ator_restrito_nao_tira_o_proprio_papel(terreno):
    """Auto-promoção: o administrador restrito zerando o próprio papel voltaria a ter o teto de admin."""
    r = terreno["ator"].put(f"/api/usuarios/{terreno['ator_id']}", json={"papel_id": None})
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text
    assert RESERVADO not in terreno["ator"].get("/api/eu").json()["privilegios"]


def test_ator_restrito_nao_promove_editor_a_administrador_sem_papel(terreno):
    r = terreno["ator"].put(
        f"/api/usuarios/{terreno['alvos']['editor']}", json={"perfil": "admin", "papel_id": None}
    )
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text


def test_ator_restrito_nao_escapa_pelo_lote(terreno):
    """O lote confere ANTES de alterar qualquer alvo: escalada é negada com 403, não contada em `recusados`."""
    r = terreno["ator"].post(
        "/api/usuarios/lote",
        json={"ids": [terreno["alvos"]["admin"]], "acao": "papel", "papel_id": terreno["papeis"]["alvo"]},
    )
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text


# ---------------------------------------------------------------- o que a regra NÃO pode quebrar
def test_papel_dentro_do_proprio_conjunto_continua_passando(terreno):
    """Conceder o que se tem segue permitido — a regra é teto, não proibição de delegar."""
    r = terreno["ator"].post(
        "/api/usuarios",
        json={"login": _login(), "nome": "Delegado", "perfil": "admin", "papel_id": terreno["papeis"]["ator"]},
    )
    assert r.status_code == 201, r.text
    novo = r.json()["usuario"]["id"]
    r = terreno["ator"].put(f"/api/usuarios/{novo}", json={"papel_id": terreno["papeis"]["ator"]})
    assert r.status_code == 200, r.text
    assert terreno["inq"].admin.delete(f"/api/usuarios/{novo}").status_code == 204


def test_administrador_pleno_continua_criando_administrador(terreno):
    r = terreno["inq"].admin.post(
        "/api/usuarios", json={"login": _login(), "nome": "Pleno", "perfil": "admin", "papel_id": None}
    )
    assert r.status_code == 201, r.text
    assert terreno["inq"].admin.delete(f"/api/usuarios/{r.json()['usuario']['id']}").status_code == 204


# ---------------------------------------------------------------- cláusula 2 (literal): o editor
def test_editor_nao_atribui_papel_administrativo(terreno):
    """Cláusula literal do portão. O 403 vem do portão de privilégio (membros.gerir/membros.papel), que o editor
    não tem em nenhum caso: `membros.*` administrativo só existe no teto do perfil admin."""
    r = terreno["editor"].post(
        "/api/usuarios",
        json={"login": _login(), "nome": "Novo", "perfil": "admin", "papel_id": terreno["papeis"]["alvo"]},
    )
    assert r.status_code == 403 and _erro(r) == "sem_privilegio", r.text
    assert r.json()["detalhe"]["exigido"] == "membros.gerir", r.text
    r = terreno["editor"].put(
        f"/api/usuarios/{terreno['alvos']['admin']}", json={"papel_id": terreno["papeis"]["alvo"]}
    )
    assert r.status_code == 403 and _erro(r) == "sem_privilegio", r.text
    assert r.json()["detalhe"]["exigido"] == "membros.papel", r.text


# ---------------------------------------------------------------- refutação exigida
def test_refutacao_um_privilegio_a_mais_em_qualquer_lugar(terreno, medida):
    """Para CADA privilégio do vocabulário: papel do ator = todos menos ele, papel alvo = todos (um a mais).

    Qualquer 2xx em criar ou editar refuta o item. Onde o privilégio que falta é o próprio `membros.gerir` ou
    `membros.papel`, o 403 vem do portão de privilégio em vez da conferência nova — continua sendo 403, e o teste
    guarda a contagem de cada motivo."""
    _definir(terreno, "alvo", set(terreno["todos"]))
    sucessos, motivos = [], {}
    for privilegio in terreno["todos"]:
        _definir(terreno, "ator", set(terreno["todos"]) - {privilegio})
        criar = terreno["ator"].post(
            "/api/usuarios",
            json={"login": _login(), "nome": "Refutação", "perfil": "admin", "papel_id": terreno["papeis"]["alvo"]},
        )
        editar = terreno["ator"].put(
            f"/api/usuarios/{terreno['alvos']['admin']}", json={"papel_id": terreno["papeis"]["alvo"]}
        )
        for rota, r in (("POST /api/usuarios", criar), ("PUT /api/usuarios/{id}", editar)):
            if r.status_code < 400:
                sucessos.append((privilegio, rota, r.status_code, r.text[:200]))
            else:
                assert r.status_code == 403, (privilegio, rota, r.status_code, r.text[:200])
                motivos[_erro(r)] = motivos.get(_erro(r), 0) + 1
    assert sucessos == [], sucessos
    gravar = medida("L0-02-g-checagem-privilegio-papel-id")
    gravar("refutacao_privilegios_testados", len(terreno["todos"]), "privilégios",
           "para cada privilégio: papel do ator = todos menos ele, papel alvo = todos")
    gravar("refutacao_chamadas_403", sum(motivos.values()), "chamadas",
           "POST e PUT /api/usuarios por privilégio; nenhuma 2xx")
    gravar("refutacao_motivos", motivos, "chamadas por erro",
           "privilegio_proprio_insuficiente = conferência nova; sem_privilegio = portão de privilégio")
