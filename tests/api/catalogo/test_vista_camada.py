"""Item `L5-32-vistas-de-camada` (linha L5 builder). Portão de pronto, cláusula por cláusula:

1. vista com filtro e 3 campos ocultos criada pela tela (a tela chama esta rota; o e2e em
   tests/e2e/test_construtor_vista.py exercita o DOM, aqui vale o contrato que ela usa);
2. consulta ao FeatureServer da vista não devolve campo oculto nem feição fora do filtro;
3. vista só leitura recusa applyEdits (403);
4. compartilhar a vista com o público não expõe a camada-mãe (teste cruzado).

Refutação do adversário: `outFields=*` e `where=1=1` na vista, e o id da camada-mãe com o token da vista —
qualquer vazamento refuta o item.
"""

from __future__ import annotations

import secrets

import pytest

from tests.api.conftest import PREFIXO_TESTE, com_token, entrar, novo_cliente
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import contexto, ids_por_slug

OCULTOS = ["cpf_do_produtor", "salario", "observacao_interna"]


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


@pytest.fixture
def mae(fabrica, conexao_plat_app, sessao_a):
    """Camada-mãe em `demo` com dois campos públicos e os três que a vista vai esconder, semeada com quatro
    feições: duas em SP (dentro do filtro da vista) e duas fora."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = fabrica.criar(
        "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "uf", "tipo": "text"},
                {"nome": "cpf_do_produtor", "tipo": "text"}, {"nome": "salario", "tipo": "double precision"},
                {"nome": "observacao_interna", "tipo": "text"}],
        geometria="Point",
    )
    feicoes = [
        ("dentro-1", "SP", "111", 10.0, "sigilo 1", -46.5, -23.5),
        ("dentro-2", "SP", "222", 20.0, "sigilo 2", -46.6, -23.6),
        ("fora-1", "RJ", "333", 30.0, "sigilo 3", -43.2, -22.9),
        ("fora-2", "MG", "444", 40.0, "sigilo 4", -43.9, -19.9),
    ]
    adds = [
        {"attributes": {"nome": n, "uf": uf, "cpf_do_produtor": cpf, "salario": s, "observacao_interna": o},
         "geometry": {"x": x, "y": y}}
        for n, uf, cpf, s, o, x, y in feicoes
    ]
    r = sessao_a.post(f"/rest/services/{item_id}/FeatureServer/0/applyEdits", json={"adds": adds})
    assert r.status_code == 200, r.text
    assert all(x["success"] for x in r.json()["addResults"]), r.text
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


def _criar_vista(sessao, mae, **kw):
    corpo = {"titulo": "zt-vista de camada", "filtro": "uf = 'SP'", "campos_ocultos": OCULTOS,
             "somente_leitura": True}
    corpo.update(kw)
    return sessao.post(f"/api/camadas/{mae['id']}/vistas", json=corpo)


@pytest.fixture
def vista(sessao_a, mae):
    r = _criar_vista(sessao_a, mae)
    assert r.status_code == 201, r.text
    return r.json()


def _colunas_da_relacao(conexao, schema: str, nome: str, tenant_id: int, usuario_id: int) -> list[str]:
    contexto(conexao, tenant_id, usuario_id=usuario_id, login="admin")
    with conexao.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                    "ORDER BY ordinal_position", (schema, nome))
        return [r["column_name"] for r in cur.fetchall()]


def _base(item_id: str) -> str:
    return f"/rest/services/{item_id}/FeatureServer/0"


# ---------------------------------------------------------------- cláusula 1
def test_vista_com_filtro_e_tres_campos_ocultos_e_uma_view_de_verdade(sessao_a, mae, conexao_plat_app, medida):
    r = _criar_vista(sessao_a, mae)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["campos_ocultos"] == OCULTOS and len(OCULTOS) == 3
    assert sorted(corpo["campos_visiveis"]) == ["nome", "uf"]

    colunas = _colunas_da_relacao(conexao_plat_app, corpo["schema"], corpo["tabela"],
                                  mae["tenant_id"], mae["admin_id"])
    assert colunas, "a view não foi criada no schema do inquilino"
    for oculto in OCULTOS:
        assert oculto not in colunas, f"{oculto} continua na definição da view"
    assert {"fid", "geom", "nome", "uf", "tenant_id"} <= set(colunas)

    contexto(conexao_plat_app, mae["tenant_id"], usuario_id=mae["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND c.relname = %s", (corpo["schema"], corpo["tabela"]))
        assert cur.fetchone()["relkind"] == "v", "a vista tem de ser uma VIEW, não uma cópia da tabela"
        cur.execute("SELECT reloptions FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND c.relname = %s", (corpo["schema"], corpo["tabela"]))
        assert "security_invoker=true" in (cur.fetchone()["reloptions"] or []), "view sem security_invoker"

    r2 = sessao_a.get(f"/api/vistas/{corpo['item_id']}")
    assert r2.status_code == 200, r2.text
    definicao = r2.json()
    assert definicao["filtro"] == "uf = 'SP'"
    assert definicao["camada_id"] == mae["id"]
    assert [c["nome"] for c in definicao["campos"] if c["nome"] in OCULTOS] == []
    medida("L5-32-vistas-de-camada")("campos_ocultos_na_view", 0, "colunas",
                                     "SELECT column_name FROM information_schema.columns (view da vista)")


# ---------------------------------------------------------------- cláusula 2 + refutação
def test_query_da_vista_nao_devolve_campo_oculto_nem_feicao_fora_do_filtro(sessao_a, vista, medida):
    r = sessao_a.get(_base(vista["item_id"]) + "/query",
                     params={"where": "1=1", "outFields": "*", "returnGeometry": "false"})
    assert r.status_code == 200, r.text
    feicoes = r.json()["features"]
    assert len(feicoes) == 2, f"filtro da vista não segurou: {feicoes}"
    assert sorted(f["attributes"]["nome"] for f in feicoes) == ["dentro-1", "dentro-2"]
    for f in feicoes:
        for oculto in OCULTOS:
            assert oculto not in f["attributes"], f"{oculto} vazou com outFields=*"
    campos = [c["name"] for c in r.json()["fields"]]
    assert not (set(OCULTOS) & set(campos)), campos

    # pedir o campo oculto pelo nome: ele não existe na relação consultada, então é recusado, nunca servido
    r2 = sessao_a.get(_base(vista["item_id"]) + "/query",
                      params={"where": "1=1", "outFields": "nome,cpf_do_produtor"})
    assert r2.status_code >= 400, r2.text
    assert "cpf_do_produtor" not in r2.text or r2.json().get("erro"), r2.text

    # filtrar PELO campo oculto também é recusado: a lista branca do where sai da view
    r3 = sessao_a.get(_base(vista["item_id"]) + "/query", params={"where": "cpf_do_produtor = '111'"})
    assert r3.status_code >= 400, r3.text

    # e nem o filtro da vista pode ser anulado por um OR do cliente pedindo as UFs de fora
    r4 = sessao_a.get(_base(vista["item_id"]) + "/query",
                      params={"where": "uf = 'RJ' OR uf = 'MG' OR uf = 'SP'", "returnCountOnly": "true"})
    assert r4.status_code == 200, r4.text
    assert r4.json()["count"] == 2, "OR do cliente passou por cima do filtro congelado da vista"

    medida("L5-32-vistas-de-camada")("feicoes_fora_do_filtro_servidas", 0, "feições",
                                     "GET /rest/services/<vista>/FeatureServer/0/query?where=1=1&outFields=*")


def test_camada_mae_continua_com_tudo(sessao_a, mae, vista):
    """Contraprova: a vista esconde, a camada-mãe não. Sem isto, um teste que só olha a vista passaria
    mesmo se os campos nunca tivessem existido."""
    r = sessao_a.get(_base(mae["id"]) + "/query", params={"where": "1=1", "outFields": "*"})
    assert r.status_code == 200, r.text
    feicoes = r.json()["features"]
    assert len(feicoes) == 4
    assert all(o in feicoes[0]["attributes"] for o in OCULTOS)


# ---------------------------------------------------------------- cláusula 3
def test_vista_somente_leitura_recusa_apply_edits(sessao_a, vista):
    r = sessao_a.post(_base(vista["item_id"]) + "/applyEdits",
                      json={"adds": [{"attributes": {"nome": "intruso", "uf": "SP"},
                                      "geometry": {"x": -46.5, "y": -23.5}}]})
    assert r.status_code == 403, r.text
    assert "somente leitura" in r.text.lower() or "vista_somente_leitura" in r.text

    r2 = sessao_a.post(f"/api/camadas/{vista['item_id']}/edicoes",
                       json={"adicionar": [{"atributos": {"nome": "intruso"},
                                            "geometria": {"type": "Point", "coordinates": [-46.5, -23.5]}}]})
    assert r2.status_code == 403, r2.text
    assert r2.json()["erro"] == "vista_somente_leitura", r2.text


def test_vista_editavel_aceita_edicao_e_recusa_feicao_fora_do_filtro(sessao_a, mae):
    r = _criar_vista(sessao_a, mae, somente_leitura=False, titulo="zt-vista editavel")
    assert r.status_code == 201, r.text
    vista_id = r.json()["item_id"]

    dentro = sessao_a.post(_base(vista_id) + "/applyEdits",
                           json={"adds": [{"attributes": {"nome": "novo-sp", "uf": "SP"},
                                           "geometry": {"x": -46.4, "y": -23.4}}]})
    assert dentro.status_code == 200, dentro.text
    assert dentro.json()["addResults"][0]["success"] is True, dentro.text

    fora = sessao_a.post(_base(vista_id) + "/applyEdits",
                         json={"adds": [{"attributes": {"nome": "novo-rj", "uf": "RJ"},
                                         "geometry": {"x": -43.2, "y": -22.9}}]})
    # WITH CASCADED CHECK OPTION: o banco recusa a linha que nasceria fora do filtro da vista
    assert fora.status_code >= 400 or fora.json()["addResults"][0]["success"] is False, fora.text


# ---------------------------------------------------------------- cláusula 4 (cruzado)
@pytest.fixture
def inquilino_publico(sessao_plat):
    """Inquilino descartável com `compartilhar_publico` LIGADO. Não é `InquilinoTemporario`: aquele gera slug
    com hífen (`zt-inq-...`) e `d_<slug>` de camada exige `^d_[a-z0-9_]+$`, então nenhuma camada nasce lá."""
    slug = f"{PREFIXO_TESTE}inq{secrets.token_hex(3)}"
    r = sessao_plat.post("/api/plataforma/inquilinos", json={
        "slug": slug, "nome": f"Inquilino de teste {slug}", "admin_login": "admin",
        "admin_nome": "Administrador de teste", "config": {"auth": {"compartilhar_publico": True}}})
    assert r.status_code == 201, r.text
    corpo = r.json()
    admin = novo_cliente()
    assert entrar(admin, slug, "admin", corpo["senha_temporaria"]).status_code == 200
    senha = "Senha-do-admin-1" + secrets.token_hex(3)
    assert admin.put("/api/eu/senha", json={"atual": corpo["senha_temporaria"], "nova": senha}).status_code == 204
    try:
        yield admin
    finally:
        sessao_plat.delete(f"/api/plataforma/inquilinos/{corpo['id']}")


def test_compartilhar_a_vista_com_o_publico_nao_expoe_a_camada_mae(inquilino_publico):
    """Inquilino próprio (descartável) com `compartilhar_publico` ligado: é o único jeito de exercitar
    `acesso = 'publico'` sem mudar a configuração dos inquilinos de demonstração, que outra suíte usa."""
    sessao = inquilino_publico
    r = sessao.post("/api/camadas/esquema", json={
        "titulo": "zt-mae do inquilino publico", "geometria": "Point", "srid": 4674,
        "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "uf", "tipo": "text"},
                   {"nome": "cpf_do_produtor", "tipo": "text"}, {"nome": "salario", "tipo": "double precision"},
                   {"nome": "observacao_interna", "tipo": "text"}],
    })
    assert r.status_code == 201, r.text
    mae_id = r.json()["item_id"]

    r = sessao.post(f"/api/camadas/{mae_id}/vistas", json={
        "titulo": "zt-vista publica", "filtro": "uf = 'SP'", "campos_ocultos": OCULTOS,
        "somente_leitura": True})
    assert r.status_code == 201, r.text
    vista_id = r.json()["item_id"]

    r = sessao.put(f"/api/itens/{vista_id}/compartilhamento", json={"acesso": "publico"})
    assert r.status_code == 200, r.text

    anon = novo_cliente()
    assert anon.get(f"/api/publico/itens/{vista_id}").status_code == 200
    assert anon.get(f"/api/publico/itens/{mae_id}").status_code == 404, "a camada-mãe ficou pública junto"

    # o item da mãe continua privado no catálogo, não só invisível na rota pública
    r = sessao.get(f"/api/itens/{mae_id}")
    assert r.status_code == 200 and r.json()["acesso"] == "privado", r.text

    # e o corpo público da vista não carrega o que ela esconde, nem o identificador da camada-mãe
    corpo = anon.get(f"/api/publico/itens/{vista_id}").text
    for oculto in OCULTOS:
        assert oculto not in corpo, f"{oculto} apareceu na ficha pública da vista"
    assert mae_id not in corpo, "o id da camada-mãe apareceu na ficha pública da vista"


def test_token_da_vista_nao_abre_a_camada_mae(sessao_a, mae, vista):
    """Refutação nomeada do item: o adversário tenta o id da camada-mãe com o token da vista."""
    r = sessao_a.post("/api/tokens", json={"nome": "zt-token da vista",
                                           "escopos": [f"camada:ler:{vista['item_id']}"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    # cliente SEM cookie: cookie + Bearer na mesma chamada é recusado como autenticação ambígua
    portador = novo_cliente()
    try:
        ok = com_token(portador, tok["token"], "GET", _base(vista["item_id"]) + "/query",
                       params={"where": "1=1", "outFields": "*"})
        assert ok.status_code == 200, ok.text
        assert len(ok.json()["features"]) == 2

        negado = com_token(portador, tok["token"], "GET", _base(mae["id"]) + "/query",
                           params={"where": "1=1", "outFields": "*"})
        assert negado.status_code == 403, negado.text
        assert "cpf_do_produtor" not in negado.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_link_anonimo_da_vista_nao_abre_a_camada_mae(sessao_a, mae, vista):
    r = sessao_a.post(f"/api/itens/{vista['item_id']}/links", json={"nome": "zt link de vista"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    anon = novo_cliente()
    assert anon.get(f"/api/compartilhado/{token}").status_code == 200
    assert anon.get(f"/api/compartilhado/{token}/itens/{mae['id']}").status_code == 404


# ---------------------------------------------------------------- fronteira de entrada
def test_ocultar_coluna_de_controle_e_recusado(sessao_a, mae):
    r = _criar_vista(sessao_a, mae, campos_ocultos=["fid"])
    assert r.status_code == 422 and r.json()["erro"] == "campo_de_controle", r.text
    r = _criar_vista(sessao_a, mae, campos_ocultos=["tenant_id"])
    assert r.status_code == 422 and r.json()["erro"] == "campo_de_controle", r.text


def test_campo_inexistente_e_filtro_invalido_sao_recusados(sessao_a, mae):
    r = _criar_vista(sessao_a, mae, campos_ocultos=["nao_existe"])
    assert r.status_code == 422 and r.json()["erro"] == "campo_inexistente", r.text
    r = _criar_vista(sessao_a, mae, filtro="uf = 'SP'; DROP TABLE plat.item")
    assert r.status_code == 422 and r.json()["erro"] == "filtro_invalido", r.text
    r = _criar_vista(sessao_a, mae, filtro="cpf_do_produtor = '111' OR 1=1")
    # filtrar pelo campo oculto na DEFINIÇÃO é legítimo (quem define a vista vê a mãe); o que não pode é o
    # cliente da vista fazer isso depois. Aqui só se exige que não vire 500.
    assert r.status_code in (201, 422), r.text


def test_vista_de_vista_e_recusada(sessao_a, mae, vista):
    r = sessao_a.post(f"/api/camadas/{vista['item_id']}/vistas",
                      json={"titulo": "zt-vista de vista", "campos_ocultos": []})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_incompativel", r.text


def test_vista_de_outro_inquilino_nao_e_encontrada(sessao_b, mae):
    r = sessao_b.post(f"/api/camadas/{mae['id']}/vistas", json={"titulo": "zt-vista cruzada"})
    assert r.status_code == 404, r.text


def test_alterar_a_vista_refaz_a_view(sessao_a, mae, vista, conexao_plat_app):
    r = sessao_a.put(f"/api/vistas/{vista['item_id']}", json={
        "titulo": "zt-vista alterada", "filtro": "uf = 'RJ'", "campos_ocultos": ["cpf_do_produtor"],
        "somente_leitura": True})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["campos_visiveis"]) == ["nome", "observacao_interna", "salario", "uf"]
    q = sessao_a.get(_base(vista["item_id"]) + "/query", params={"where": "1=1", "outFields": "*"})
    assert q.status_code == 200, q.text
    assert [f["attributes"]["nome"] for f in q.json()["features"]] == ["fora-1"]
    assert "cpf_do_produtor" not in q.text
