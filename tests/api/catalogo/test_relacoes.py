"""Relações (L0-03-i; ADR 0004 seção 5): camada → mapa → app; usado-por profundidade 2; DELETE sem cascata 409 com
a lista; com cascata na ordem certa (evento por item); ciclo 409 com caminho; outro inquilino/invisível 422;
vocabulário fora 422; família incompatível 422; FK sem órfã após expurgo; medida usado_por_p95_ms."""

import time

from tests.api.catalogo.conftest import documento_mapa, titulo_zt

ITEM = "L0-03-catalogo"


def _grafo(itens_a):
    cam = itens_a.criar("camada_vetorial", titulo=titulo_zt("camada"))
    mapa = itens_a.criar(
        "mapa", titulo=titulo_zt("mapa"), dados=documento_mapa(cam["id"])
    )
    app = itens_a.criar(
        "app", titulo=titulo_zt("app"), dados={"tipo": "app", "esquema_versao": 1, "corpo": {"mapas": [mapa["id"]]}}
    )
    return cam, mapa, app


def test_usado_por_ordem_e_exclusao(sessao_a, itens_a, medida):
    cam, mapa, app = _grafo(itens_a)
    r = sessao_a.get(f"/api/itens/{cam['id']}/usado-por")
    assert r.status_code == 200
    linhas = {x["id"]: x for x in r.json()}
    assert linhas[mapa["id"]]["profundidade"] == 1 and linhas[mapa["id"]]["tipo_relacao"] == "camada_de_mapa"
    assert linhas[app["id"]]["profundidade"] == 2 and linhas[app["id"]]["caminho"] == [cam["id"], mapa["id"], app["id"]]
    assert sessao_a.get(f"/api/itens/{cam['id']}/usado-por?profundidade=1").json()[0]["id"] == mapa["id"]
    assert sessao_a.get(f"/api/itens/{cam['id']}").json()["usado_por"] == 1
    assert [x["id"] for x in sessao_a.get(f"/api/itens/{mapa['id']}/criado-a-partir-de").json()] == [cam["id"]]
    ordem = sessao_a.get(f"/api/itens/{cam['id']}/ordem-de-exclusao").json()
    assert [x["id"] for x in ordem["ordem"]] == [app["id"], mapa["id"]] and ordem["ocultos"] == 0
    r = sessao_a.delete(f"/api/itens/{cam['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "possui_dependentes"
    assert [x["id"] for x in r.json()["detalhe"]["ordem"]] == [app["id"], mapa["id"]]
    t0 = time.perf_counter()
    for _ in range(20):
        sessao_a.get(f"/api/itens/{cam['id']}/usado-por")
    p = (time.perf_counter() - t0) * 1000 / 20
    medida(ITEM)(
        "usado_por_medio_ms", round(p, 1), "ms", "GET /api/itens/{id}/usado-por, média de 20 chamadas HTTP (grafo de 3)"
    )
    r = sessao_a.delete(f"/api/itens/{cam['id']}?cascata=true")
    assert r.status_code == 204
    for x in (cam, mapa, app):
        assert sessao_a.get(f"/api/itens/{x['id']}").status_code == 404
    eventos = sessao_a.get("/api/eventos?limite=20").json()["itens"]
    apagados = [e["alvo_id"] for e in eventos if e["tipo"] == "itens/apagar"][:3]
    assert set(apagados) == {app["id"], mapa["id"], cam["id"]}
    assert apagados.index(app["id"]) > apagados.index(cam["id"])  # o mais recente vem primeiro: cam foi o último


def test_dependente_invisivel_bloqueia_sem_revelar(sessao_a, itens_a, editor_a):
    dono_c, _ = editor_a
    cam = itens_a.criar("camada_vetorial", sessao=dono_c)
    sessao_a.put(f"/api/itens/{cam['id']}/compartilhamento", json={"acesso": "inquilino"})
    dono_c.get(f"/api/itens/{cam['id']}")
    # o admin cria um mapa privado que usa a camada do editor
    mapa = itens_a.criar("mapa", dados=documento_mapa(cam["id"]))
    r = dono_c.get(f"/api/itens/{cam['id']}/usado-por")
    assert r.json() == [
        {
            "id": mapa["id"],
            "oculto": True,
            "tipo_relacao": "camada_de_mapa",
            "profundidade": 1,
            "caminho": [cam["id"], mapa["id"]],
            "apaga_junto": False,
        }
    ]
    r = dono_c.delete(f"/api/itens/{cam['id']}?cascata=true")
    assert r.status_code == 409 and r.json()["detalhe"]["ocultos"] == 1 and r.json()["detalhe"]["ordem"] == []


def test_ciclo_vocabulario_familia_e_outro_inquilino(sessao_a, itens_a, itens_b):
    cam = itens_a.criar("camada_vetorial")
    vista = itens_a.criar("vista_de_camada", dados={"camada_id": cam["id"]})
    # ciclo: camada dependeria da vista que depende dela → 409
    r = sessao_a.put(
        f"/api/itens/{cam['id']}/relacoes", json={"relacoes": [{"destino": vista["id"], "tipo": "dado_de_camada"}]}
    )
    assert r.status_code in (409, 422), (
        r.text
    )  # família camada→camada não vale para dado_de_camada (422) ou ciclo (409)
    arq = itens_a.criar("arquivo")
    est = itens_a.criar("estilo")
    r = sessao_a.put(
        f"/api/itens/{est['id']}/relacoes", json={"relacoes": [{"destino": cam["id"], "tipo": "estilo_de_camada"}]}
    )
    assert r.status_code == 200 and r.json()[0]["id"] == cam["id"]
    r = sessao_a.put(
        f"/api/itens/{arq['id']}/relacoes", json={"relacoes": [{"destino": est["id"], "tipo": "anexo_de_item"}]}
    )
    assert r.status_code == 200
    # agora cam → arq por dado_de_camada fecharia o ciclo cam ← est ← arq ← cam
    r = sessao_a.put(
        f"/api/itens/{cam['id']}/relacoes", json={"relacoes": [{"destino": arq["id"], "tipo": "dado_de_camada"}]}
    )
    assert r.status_code == 409 and r.json()["erro"] == "relacao_ciclo" and len(r.json()["detalhe"]["caminho"]) >= 3, (
        r.text
    )
    r = sessao_a.put(
        f"/api/itens/{est['id']}/relacoes", json={"relacoes": [{"destino": cam["id"], "tipo": "nao_existe"}]}
    )
    assert r.status_code == 422 and r.json()["erro"] == "relacao_familia_invalida"
    r = sessao_a.put(
        f"/api/itens/{est['id']}/relacoes", json={"relacoes": [{"destino": arq["id"], "tipo": "estilo_de_camada"}]}
    )
    assert (
        r.status_code == 422 and r.json()["erro"] == "relacao_familia_invalida"
    )  # estilo → arquivo não é família de destino
    de_b = itens_b.criar("camada_vetorial")
    r = sessao_a.put(
        f"/api/itens/{est['id']}/relacoes", json={"relacoes": [{"destino": de_b["id"], "tipo": "estilo_de_camada"}]}
    )
    assert r.status_code == 422 and r.json()["erro"] == "relacao_com_outro_inquilino"
    r = sessao_a.put(
        f"/api/itens/{cam['id']}/relacoes", json={"relacoes": [{"destino": cam["id"], "tipo": "dado_de_camada"}]}
    )
    assert r.status_code == 422
    # tipo com extrator: relações vêm de dados, PUT direto recusado
    mapa = itens_a.criar("mapa")
    r = sessao_a.put(f"/api/itens/{mapa['id']}/relacoes", json={"relacoes": []})
    assert r.status_code == 409 and r.json()["erro"] == "relacoes_pelo_tipo"


def test_relacao_some_com_o_dado_e_sem_orfa_no_expurgo(sessao_a, itens_a, conexao_plat_app):
    cam = itens_a.criar("camada_vetorial")
    mapa = itens_a.criar("mapa", dados=documento_mapa(cam["id"]))
    assert sessao_a.get(f"/api/itens/{cam['id']}").json()["usado_por"] == 1
    r = sessao_a.put(f"/api/itens/{mapa['id']}", json={"dados": documento_mapa()})
    assert r.status_code == 200
    assert sessao_a.get(f"/api/itens/{cam['id']}").json()["usado_por"] == 0
    sessao_a.put(f"/api/itens/{mapa['id']}", json={"dados": documento_mapa(cam["id"])})
    assert sessao_a.delete(f"/api/itens/{mapa['id']}").status_code == 204
    from tests.api.test_rls import contexto, ids_por_slug

    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.item_expurgar(%s::uuid) AS ok", (mapa["id"],))
        assert cur.fetchone()["ok"] is True
        cur.execute(
            "SELECT count(*) AS n FROM plat.item_relacao WHERE origem = %s::uuid OR destino = %s::uuid",
            (mapa["id"], mapa["id"]),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (mapa["id"],))
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.commit()
    itens_a.criados.remove(mapa["id"])
