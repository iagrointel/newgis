"""Modelo do item (L0-03-a; ADR 0004 seções 2, 3, 13): CRUD, uuid estável em PUT e em mover, tipo inexistente 422,
resumo de 5.000 → 422, descrição com <script> → texto inerte, extent fora de faixa → 422, PUT trocando tenant_id/
dono_id → 400, dados inválido → 422 com campo, id fornecido (ADR 0005) aceito, tipo_item sem escrita por plat_app,
versão conflitante 409, cota. A medida lista_tipo_p95_ms vive em test_busca.py (corpus semeado)."""

import uuid

import psycopg2
import pytest

from tests.api.catalogo.conftest import DADOS_POR_TIPO, titulo_zt
from tests.api.test_rls import contexto, ids_por_slug


def test_ciclo_crud_uuid_estavel(sessao_a, itens_a):
    it = itens_a.criar(
        "mapa",
        resumo="r",
        tags=["ibge", "x"],
        descricao="# T\n<script>alert(1)</script> **b**",
        extent=[-50, -20, -40, -10],
    )
    iid = it["id"]
    assert uuid.UUID(iid) and it["versao_atual"] == 1 and it["pontuacao"] >= 3 and it["familia"] == "mapa"
    assert "<script" not in it["descricao_html"] and "<strong>b</strong>" in it["descricao_html"]
    assert it["extent"] == [-50.0, -20.0, -40.0, -10.0] and it["extent_origem"] == "usuario"
    assert it["pode_editar"] and it["pode_apagar"] and it["acesso"] == "privado"
    r = sessao_a.put(f"/api/itens/{iid}", json={"titulo": titulo_zt("v2"), "tags": ["a", "b", "c"]})
    assert r.status_code == 200 and r.json()["id"] == iid and r.json()["versao_atual"] == 2
    r = sessao_a.patch(f"/api/itens/{iid}", json={"resumo": "novo"})
    assert r.status_code == 200 and r.json()["resumo"] == "novo" and r.json()["versao_atual"] == 3
    r = sessao_a.post("/api/pastas", json={"nome": titulo_zt("pasta")})
    pid = r.json()["id"]
    r = sessao_a.post(f"/api/itens/{iid}/mover", json={"pasta_id": pid})
    assert r.status_code == 200 and r.json()["id"] == iid and r.json()["pasta"]["id"] == pid
    assert sessao_a.get(f"/api/itens/{iid}").json()["versao_atual"] == 3  # mover não versiona
    r = sessao_a.delete(f"/api/itens/{iid}")
    assert r.status_code == 204
    assert sessao_a.get(f"/api/itens/{iid}").status_code == 404
    assert sessao_a.post(f"/api/itens/{iid}/mover", json={"pasta_id": None}).status_code == 404


@pytest.mark.parametrize(
    "corpo,status,erro,campo",
    [
        ({"tipo": "inexistente", "titulo": "x"}, 422, "tipo_inexistente", None),
        (
            {"tipo": "mapa", "titulo": "x", "resumo": "a" * 5000, "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.resumo",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "extent": [-200, 0, 1, 1], "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.extent",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "extent": [10, 0, 1, 1], "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.extent",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "tags": ["a,b"], "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.tags",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "tags": [str(i) for i in range(51)], "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.tags",
        ),
        (
            {
                "tipo": "mapa",
                "titulo": "x",
                "categorias": [str(uuid.uuid4()) for _ in range(21)],
                "dados": DADOS_POR_TIPO["mapa"],
            },
            422,
            "validacao",
            "body.categorias",
        ),
        ({"tipo": "mapa", "titulo": "x", "dados": {"esquema_versao": 1}}, 422, "dados_invalidos", "(raiz)"),
        (
            {"tipo": "mapa", "titulo": "x", "dados": {"esquema_versao": 1, "corpo": {}, "extra": 1}},
            422,
            "dados_invalidos",
            "(raiz)",
        ),
        (
            {"tipo": "arquivo", "titulo": "x", "dados": {**DADOS_POR_TIPO["arquivo"], "sha256": "zz"}},
            422,
            "dados_invalidos",
            "sha256",
        ),
        (
            {
                "tipo": "camada_vetorial",
                "titulo": "x",
                "dados": {**DADOS_POR_TIPO["camada_vetorial"], "campos": [{"nome": 1, "tipo": "t"}]},
            },
            422,
            "dados_invalidos",
            "campos.0.nome",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "url": "ftp://x", "dados": DADOS_POR_TIPO["mapa"]},
            422,
            "validacao",
            "body.url",
        ),
        (
            {"tipo": "mapa", "titulo": "x", "pasta_id": str(uuid.uuid4()), "dados": DADOS_POR_TIPO["mapa"]},
            404,
            "pasta_inexistente",
            None,
        ),
        (
            {"tipo": "mapa", "titulo": "x", "categorias": [str(uuid.uuid4())], "dados": DADOS_POR_TIPO["mapa"]},
            404,
            "categoria_inexistente",
            None,
        ),
        (
            {"tipo": "mapa", "titulo": "x", "dados": DADOS_POR_TIPO["mapa"], "tenant_id": 1},
            422,
            "validacao",
            "body.tenant_id",
        ),
    ],
)
def test_criacao_recusada_com_mensagem(sessao_a, corpo, status, erro, campo):
    corpo = {**corpo, "titulo": titulo_zt(corpo["titulo"])}
    r = sessao_a.post("/api/itens", json=corpo)
    assert r.status_code == status and r.json()["erro"] == erro, r.text
    if campo:
        campos = [d["campo"] for d in r.json()["detalhe"]]
        assert campo in campos, campos


def test_put_campos_imutaveis_e_dono(sessao_a, itens_a, ids):
    it = itens_a.criar("mapa")
    for campo in ("tenant_id", "id", "dono_id", "criado_em", "busca", "apagado_em", "tamanho_bytes", "pontuacao"):
        r = sessao_a.put(f"/api/itens/{it['id']}", json={campo: 1})
        assert r.status_code == 400 and r.json()["erro"] == "campo_nao_editavel" and campo in r.json()["detalhe"], (
            campo,
            r.text,
        )
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"titulo": "x", "versao_atual": 99})
    assert r.status_code == 409 and r.json()["erro"] == "versao_conflito"
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"titulo": titulo_zt("ok"), "versao_atual": 1})
    assert r.status_code == 200 and r.json()["versao_atual"] == 2


def test_id_fornecido_e_conflito(sessao_a, itens_a):
    iid = str(uuid.uuid4())
    it = itens_a.criar("mapa", id=iid)
    assert it["id"] == iid
    r = sessao_a.post(
        "/api/itens", json={"tipo": "mapa", "titulo": titulo_zt(), "dados": DADOS_POR_TIPO["mapa"], "id": iid}
    )
    assert r.status_code == 409


def test_visualizador_nao_cria_e_editor_publica_camada_so_com_privilegio(visualizador_a, editor_a, itens_a):
    c, _ = visualizador_a
    r = c.post("/api/itens", json={"tipo": "mapa", "titulo": titulo_zt(), "dados": DADOS_POR_TIPO["mapa"]})
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"
    e, _ = editor_a
    it = itens_a.criar("camada_vetorial", sessao=e)
    assert it["tipo"] == "camada_vetorial"


def test_tipo_item_e_vocabulario_sem_escrita(conexao_plat_app, cliente, sessao_a):
    r = sessao_a.get("/api/tipos-item")
    assert r.status_code == 200 and len(r.json()) == 15  # 14 do L0-03 + narrativa (L5-04-a)
    nomes = {t["nome"] for t in r.json()}
    assert {
        "narrativa",
        "camada_vetorial",
        "vista_de_camada",
        "raster",
        "mapa",
        "cena",
        "estilo",
        "app",
        "painel",
        "formulario",
        "fluxo",
        "rede",
        "conexao",
        "arquivo",
        "modelo_amc",
    } == nomes
    assert all(t["esquema"].get("additionalProperties") is False for t in r.json())
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    for sql in (
        "INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, icone, modulo_front, linha_dona) "
        "VALUES ('zz', 'mapa', 'x', 'x', '{}', 'x', 'x', 'x')",
        "UPDATE plat.tipo_item SET rotulo = 'x'",
        "DELETE FROM plat.relacao_tipo",
        "INSERT INTO plat.item_versao(item_id, versao, tenant_id, corpo, sha256) "
        "VALUES (gen_random_uuid(), 1, 1, '{}', 'x')",
    ):
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql)
        conexao_plat_app.rollback()


def test_lista_paginada_com_cursor_e_deslocamento(sessao_a, itens_a):
    for _ in range(5):
        # o mesmo termo "cursor" em todos: o FTS indexa palavra inteira (cursor0 não casa com cursor)
        itens_a.criar("conexao", titulo=titulo_zt("cursor"))
    r = sessao_a.get("/api/itens?q=cursor&tipo=conexao&limite=2&ordenar=titulo&direcao=asc")
    assert r.status_code == 200
    j = r.json()
    assert j["total"] >= 5 and len(j["itens"]) == 2 and j["proximo_cursor"]
    assert 'rel="next"' in r.headers.get("link", "")
    r2 = sessao_a.get(
        f"/api/itens?q=cursor&tipo=conexao&limite=2&ordenar=titulo&direcao=asc&cursor={j['proximo_cursor']}"
    )
    assert r2.status_code == 200
    ids1 = {x["id"] for x in j["itens"]}
    ids2 = {x["id"] for x in r2.json()["itens"]}
    assert not (ids1 & ids2) and len(ids2) == 2
    r3 = sessao_a.get(f"/api/itens?q=outra&cursor={j['proximo_cursor']}")
    assert r3.status_code == 400 and r3.json()["erro"] == "cursor_invalido"
    r4 = sessao_a.get("/api/itens?deslocamento=10001")
    assert r4.status_code == 422 and r4.json()["erro"] == "deslocamento_alto"
    r5 = sessao_a.get("/api/itens?limite=201")
    assert r5.status_code == 422
    # deslocamento comum ainda funciona
    r6 = sessao_a.get("/api/itens?q=cursor&tipo=conexao&limite=2&deslocamento=2&ordenar=titulo&direcao=asc")
    assert {x["id"] for x in r6.json()["itens"]} == ids2


def test_lista_omite_descricao_e_dados(sessao_a, itens_a):
    it = itens_a.criar("mapa", descricao="texto")
    r = sessao_a.get(f"/api/itens?q=id:{it['id']}")
    linha = r.json()["itens"][0]
    assert "descricao" not in linha and "dados" not in linha and linha["id"] == it["id"]
    assert set(sessao_a.get(f"/api/itens/{it['id']}").json()) >= {
        "descricao",
        "descricao_html",
        "dados",
        "termos_de_uso",
    }


def test_token_catalogo_ler_le_mas_nao_escreve(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = sessao_a.post("/api/tokens", json={"nome": "zt-cat-ler", "escopos": ["catalogo:ler"]})
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    from tests.api.conftest import novo_cliente

    c = novo_cliente()
    assert c.get(f"/api/itens/{it['id']}", headers=h).status_code == 200
    assert c.get("/api/itens?limite=1", headers=h).status_code == 200
    r = c.put(f"/api/itens/{it['id']}", headers=h, json={"titulo": "x"})
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
    # escopo com uuid: item inexistente ou de outro inquilino = 422 na criação do token
    r = sessao_a.post("/api/tokens", json={"nome": "zt-cat-uuid", "escopos": [f"camada:ler:{uuid.uuid4()}"]})
    assert r.status_code == 422 and r.json()["erro"] == "escopo_item_inexistente"
    r = sessao_a.post("/api/tokens", json={"nome": "zt-cat-uuid2", "escopos": [f"camada:ler:{it['id']}"]})
    assert r.status_code == 201
    sessao_a.delete(f"/api/tokens/{r.json()['id']}")
