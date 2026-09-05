"""Transferência de dono (L0-03-j; ADR 0004 seção 10): 3 itens com 1 falha prevista (novo dono fora do grupo) → o
plano mostra e adicionar_aos_grupos resolve; camada leva 2 vistas; só a vista = 409 vista_sem_camada; tudo de um
usuário e apagá-lo em seguida; uuid e compartilhamentos iguais; link sobrevive; desabilitado 422; outro inquilino 404;
mapa que usa a camada NÃO muda de dono."""

from tests.api.catalogo.conftest import titulo_zt
from tests.api.conftest import novo_cliente


def test_plano_com_falha_e_solucao(sessao_a, itens_a, usuarios_a, editor_a):
    dono_c, dono = editor_a
    novo_c, novo, _ = usuarios_a.sessao("editor")
    g = dono_c.post("/api/grupos", json={"nome": titulo_zt("g-transf"), "entrada": "convite"}).json()
    a, b, c = (itens_a.criar("mapa", sessao=dono_c) for _ in range(3))
    assert dono_c.put(f"/api/itens/{c['id']}/compartilhamento", json={"grupos": [g["id"]]}).status_code == 200
    tok = dono_c.post(f"/api/itens/{c['id']}/links", json={}).json()["token"]
    antes = dono_c.get(f"/api/itens/{c['id']}/compartilhamento").json()
    r = dono_c.post(
        "/api/itens/transferir", json={"ids": [a["id"], b["id"], c["id"]], "novo_dono_id": novo["id"], "simular": True}
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] == 3 and j["com_falha"] == 1 and j["executado"] is False
    falha = next(p for p in j["plano"] if p["id"] == c["id"])["falhas"][0]
    assert (
        falha["codigo"] == "novo_dono_fora_do_grupo"
        and falha["grupo"]["id"] == g["id"]
        and falha["solucao"] == "adicionar_aos_grupos"
    )
    r = dono_c.post(
        "/api/itens/transferir", json={"ids": [a["id"], b["id"], c["id"]], "novo_dono_id": novo["id"], "simular": False}
    )
    assert r.status_code == 409 and r.json()["erro"] == "plano_com_falhas"
    r = dono_c.post(
        "/api/itens/transferir",
        json={
            "ids": [a["id"], b["id"], c["id"]],
            "novo_dono_id": novo["id"],
            "simular": False,
            "adicionar_aos_grupos": True,
        },
    )
    assert r.status_code == 200 and r.json()["executado"] and r.json()["transferidos"] == 3, r.text
    for it in (a, b, c):
        j = novo_c.get(f"/api/itens/{it['id']}").json()
        assert j["id"] == it["id"] and j["dono"]["id"] == novo["id"] and j["pode_editar"]
    assert dono_c.get(f"/api/itens/{a['id']}").status_code == 404  # o antigo dono deixou de ver o item privado
    depois = novo_c.get(f"/api/itens/{c['id']}/compartilhamento").json()
    assert [x["id"] for x in depois["grupos"]] == [x["id"] for x in antes["grupos"]] and depois["acesso"] == antes[
        "acesso"
    ]
    assert [x["id"] for x in depois["links"]] == [x["id"] for x in antes["links"]]
    assert novo_cliente().get(f"/api/compartilhado/{tok}").status_code == 200  # o link sobrevive
    ev = [e for e in sessao_a.get("/api/eventos?limite=20").json()["itens"] if e["tipo"] == "itens/transferir"]
    assert len(ev) >= 3 and ev[0]["propriedades"]["de"] == dono["id"] and ev[0]["propriedades"]["para"] == novo["id"]


def test_camada_arrasta_vistas_e_vista_sozinha_recusa(sessao_a, itens_a, usuarios_a):
    novo_c, novo, _ = usuarios_a.sessao("editor")
    cam = itens_a.criar("camada_vetorial")
    v1 = itens_a.criar("vista_de_camada", dados={"camada_id": cam["id"]})
    v2 = itens_a.criar("vista_de_camada", dados={"camada_id": cam["id"]})
    mapa = itens_a.criar("mapa", dados={"esquema_versao": 1, "corpo": {"camadas": [cam["id"]]}})
    r = sessao_a.post("/api/itens/transferir", json={"ids": [v1["id"]], "novo_dono_id": novo["id"], "simular": True})
    assert r.json()["plano"][0]["falhas"][0]["codigo"] == "vista_sem_camada"
    r = sessao_a.post("/api/itens/transferir", json={"ids": [v1["id"]], "novo_dono_id": novo["id"], "simular": False})
    assert r.status_code == 409
    r = sessao_a.post("/api/itens/transferir", json={"ids": [cam["id"]], "novo_dono_id": novo["id"], "simular": False})
    assert r.status_code == 200 and r.json()["executado"], r.text
    assert {x["id"] for x in r.json()["plano"][0]["arrasta"]} == {v1["id"], v2["id"]}
    for it in (cam, v1, v2):
        assert novo_c.get(f"/api/itens/{it['id']}").json()["dono"]["id"] == novo["id"]
    assert sessao_a.get(f"/api/itens/{mapa['id']}").json()["dono"]["id"] != novo["id"]  # o mapa não muda de dono


def test_tudo_de_um_usuario_e_apagar_usuario(sessao_a, itens_a, usuarios_a):
    origem_c, origem, _ = usuarios_a.sessao("editor")
    destino_c, destino, _ = usuarios_a.sessao("editor")
    for _ in range(2):
        itens_a.criar("mapa", sessao=origem_c)
    r = sessao_a.post(
        "/api/itens/transferir",
        json={"usuario_origem_id": origem["id"], "novo_dono_id": destino["id"], "simular": False, "pastas": "unica"},
    )
    assert r.status_code == 200 and r.json()["transferidos"] == 2, r.text
    itens = destino_c.get("/api/itens?meus=true&limite=50").json()["itens"]
    assert len([i for i in itens if i["pasta"] and i["pasta"]["nome"] == f"de_{origem['login']}"]) == 2
    r = sessao_a.delete(f"/api/usuarios/{origem['id']}")
    assert r.status_code == 204, r.text
    usuarios_a.criados.remove(origem["id"])


def test_recusas(sessao_a, sessao_b, itens_a, itens_b, usuarios_a, ids):
    it = itens_a.criar("mapa")
    inativo_c, inativo, _ = usuarios_a.sessao("editor")
    assert sessao_a.put(f"/api/usuarios/{inativo['id']}", json={"ativo": False}).status_code == 200
    r = sessao_a.post("/api/itens/transferir", json={"ids": [it["id"]], "novo_dono_id": inativo["id"], "simular": True})
    assert r.status_code == 422 and r.json()["erro"] == "novo_dono_inativo"
    vis_c, vis, _ = usuarios_a.sessao("visualizador")
    r = sessao_a.post("/api/itens/transferir", json={"ids": [it["id"]], "novo_dono_id": vis["id"], "simular": True})
    assert r.status_code == 422 and r.json()["erro"] == "novo_dono_sem_privilegio"
    de_b = itens_b.criar("mapa")
    r = sessao_a.post(
        "/api/itens/transferir", json={"ids": [de_b["id"]], "novo_dono_id": ids["a"]["id"], "simular": True}
    )
    assert r.status_code == 404
    r = sessao_a.post(
        "/api/itens/transferir", json={"ids": [it["id"]], "novo_dono_id": ids["b"]["id"], "simular": True}
    )
    assert r.status_code == 404  # usuário de outro inquilino não existe aqui
    r = sessao_a.post("/api/itens/transferir", json={"novo_dono_id": ids["a"]["id"], "simular": True})
    assert r.status_code == 422
    r = vis_c.post("/api/itens/transferir", json={"ids": [it["id"]], "novo_dono_id": ids["a"]["id"], "simular": True})
    assert r.status_code == 403
