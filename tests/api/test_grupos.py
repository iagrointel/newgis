"""Grupos (ADR 0002 seções 4, 16.5): criar, convidar, aceitar, pedir/aprovar, sair, administrativo recusa sair,
protegido recusa apagar, convite a usuário de outro inquilino = 404, membro comum não convida (403), gerente não
vira dono por /membros/{uid} (409), transferência de dono, visibilidade por RLS."""

import secrets

from tests.api.conftest import PREFIXO_TESTE


def _nome():
    return f"{PREFIXO_TESTE}-grupo-{secrets.token_hex(3)}"


def test_ciclo_de_vida_completo(sessao_a, usuarios_a, ids):
    dono_c, dono, _ = usuarios_a.sessao("editor")
    m1_c, m1, _ = usuarios_a.sessao("visualizador")
    m2_c, m2, _ = usuarios_a.sessao("campo")
    r = dono_c.post(
        "/api/grupos", json={"nome": _nome(), "visibilidade": "membros", "entrada": "convite", "tags": ["a", "b"]}
    )
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["dono"]["id"] == dono["id"] and g["meu_papel"] == "dono" and g["membros"] == 1 and g["tags"] == ["a", "b"]
    assert dono_c.post("/api/grupos", json={"nome": g["nome"].upper()}).status_code == 409
    # visibilidade membros: m1 não vê; admin (gerir_todos) vê
    assert m1_c.get(f"/api/grupos/{g['id']}").status_code == 404
    assert sessao_a.get(f"/api/grupos/{g['id']}").status_code == 200
    # membro comum não convida; visualizador sem grupos.criar não cria
    assert m1_c.post("/api/grupos", json={"nome": _nome()}).status_code == 403
    # convite → aparece em /api/eu/convites → aceita
    r = dono_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": m1["id"]})
    assert r.status_code == 201 and r.json() == {"estado": "convidado"}
    assert dono_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": m1["id"]}).status_code == 409
    convites = m1_c.get("/api/eu/convites").json()
    assert convites[0]["grupo"]["id"] == g["id"] and convites[0]["convidado_por"]["id"] == dono["id"]
    assert m1_c.get(f"/api/grupos/{g['id']}").json()["meu_estado"] == "convidado"  # convidado vê o grupo
    assert m1_c.get(f"/api/grupos/{g['id']}/membros").status_code == 404  # mas não a lista, até aceitar
    assert m1_c.post(f"/api/grupos/{g['id']}/aceitar").json() == {"estado": "ativo"}
    assert m1_c.post(f"/api/grupos/{g['id']}/aceitar").status_code == 404
    assert m1_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": m2["id"]}).status_code == 403
    # entrada por convite: m2 não entra sozinho
    assert m2_c.post(f"/api/grupos/{g['id']}/entrar").status_code == 404  # nem vê (visibilidade membros)
    r = dono_c.put(f"/api/grupos/{g['id']}", json={"visibilidade": "inquilino"})
    assert r.status_code == 200 and r.json()["visibilidade"] == "inquilino"
    r = m2_c.post(f"/api/grupos/{g['id']}/entrar")
    assert r.status_code == 403 and r.json()["erro"] == "entrada_por_convite"
    # entrada por pedido → aprovar
    dono_c.put(f"/api/grupos/{g['id']}", json={"entrada": "pedido"})
    r = m2_c.post(f"/api/grupos/{g['id']}/entrar")
    assert r.status_code == 202 and r.json() == {"estado": "pedido"}
    assert m1_c.post(f"/api/grupos/{g['id']}/membros/{m2['id']}/aprovar").status_code == 403
    assert dono_c.post(f"/api/grupos/{g['id']}/membros/{m1['id']}/aprovar").status_code == 404  # sem pedido
    assert dono_c.post(f"/api/grupos/{g['id']}/membros/{m2['id']}/aprovar").json() == {"estado": "ativo"}
    membros = dono_c.get(f"/api/grupos/{g['id']}/membros").json()
    assert [m["papel"] for m in membros] == ["dono", "membro", "membro"] and membros[0]["usuario"]["id"] == dono["id"]
    # gerente: promove, mas não vira dono por /membros
    assert dono_c.put(f"/api/grupos/{g['id']}/membros/{m1['id']}", json={"papel": "gerente"}).status_code == 200
    r = m1_c.put(f"/api/grupos/{g['id']}/membros/{dono['id']}", json={"papel": "membro"})
    assert r.status_code == 409 and r.json()["erro"] == "papel_dono_via_grupo"
    assert (
        m1_c.put(f"/api/grupos/{g['id']}/membros/{m2['id']}", json={"papel": "gerente"}).status_code == 200
    )  # gerente promove
    assert m1_c.delete(f"/api/grupos/{g['id']}").status_code == 403  # gerente não apaga
    # dono não sai; membro sai; gerente remove
    r = dono_c.delete(f"/api/grupos/{g['id']}/membros/{dono['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "dono_nao_sai"
    assert m2_c.delete(f"/api/grupos/{g['id']}/membros/{m2['id']}").status_code == 204
    assert m2_c.get(f"/api/grupos/{g['id']}").json()["meu_estado"] is None
    # transferência: novo dono tem de ser membro ativo; o antigo vira gerente
    r = dono_c.put(f"/api/grupos/{g['id']}", json={"dono_id": m2["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "novo_dono_nao_membro"
    assert m1_c.put(f"/api/grupos/{g['id']}", json={"dono_id": m1["id"]}).status_code == 403  # gerente não transfere
    r = dono_c.put(f"/api/grupos/{g['id']}", json={"dono_id": m1["id"]})
    assert r.status_code == 200 and r.json()["dono"]["id"] == m1["id"]
    papeis = {m["usuario"]["id"]: m["papel"] for m in m1_c.get(f"/api/grupos/{g['id']}/membros").json()}
    assert papeis[m1["id"]] == "dono" and papeis[dono["id"]] == "gerente"
    # protegido não se apaga; depois de desproteger, o dono apaga
    m1_c.put(f"/api/grupos/{g['id']}", json={"protegido": True})
    r = m1_c.delete(f"/api/grupos/{g['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "grupo_protegido"
    m1_c.put(f"/api/grupos/{g['id']}", json={"protegido": False})
    assert m1_c.delete(f"/api/grupos/{g['id']}").status_code == 204
    assert m1_c.get(f"/api/grupos/{g['id']}").status_code == 404
    assert m1_c.get("/api/grupos/nao-e-uuid").status_code == 404
    tipos = {e["tipo"] for e in sessao_a.get("/api/eventos?limite=100").json()["itens"]}
    assert {
        "grupos/criar",
        "grupos/convidar",
        "grupos/entrar",
        "grupos/pedir",
        "grupos/aprovar",
        "grupos/papel",
        "grupos/sair",
        "grupos/transferir",
        "grupos/apagar",
        "grupos/atualizar",
    } <= tipos


def test_entrada_livre_recusar_convite_e_remover(sessao_a, usuarios_a):
    dono_c, dono, _ = usuarios_a.sessao("editor")
    m_c, m, _ = usuarios_a.sessao("visualizador")
    g = dono_c.post("/api/grupos", json={"nome": _nome(), "visibilidade": "inquilino", "entrada": "livre"}).json()
    r = m_c.post(f"/api/grupos/{g['id']}/entrar")
    assert r.status_code == 200 and r.json() == {"estado": "ativo"}
    assert m_c.post(f"/api/grupos/{g['id']}/entrar").status_code == 409
    assert dono_c.delete(f"/api/grupos/{g['id']}/membros/{m['id']}").status_code == 204
    assert dono_c.delete(f"/api/grupos/{g['id']}/membros/{m['id']}").status_code == 404
    dono_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": m["id"], "papel": "gerente"})
    assert m_c.post(f"/api/grupos/{g['id']}/recusar").status_code == 204
    assert m_c.post(f"/api/grupos/{g['id']}/recusar").status_code == 404
    assert m_c.get("/api/eu/convites") == [] or m_c.get("/api/eu/convites").json() == []
    lista = m_c.get("/api/grupos?meus=1").json()
    assert all(i["meu_estado"] for i in lista["itens"])
    assert dono_c.delete(f"/api/grupos/{g['id']}").status_code == 204


def test_administrativo_atualizacao_compartilhada_e_privilegios(sessao_a, usuarios_a):
    ed_c, ed, _ = usuarios_a.sessao("editor")
    assert ed_c.post("/api/grupos", json={"nome": _nome(), "administrativo": True}).status_code == 403
    r = ed_c.post("/api/grupos", json={"nome": _nome(), "atualizacao_compartilhada": True, "entrada": "livre"})
    assert r.status_code == 422 and r.json()["erro"] == "atualizacao_exige_convite_ou_pedido"
    r = ed_c.post("/api/grupos", json={"nome": _nome(), "atualizacao_compartilhada": True, "entrada": "convite"})
    assert r.status_code == 201
    g = r.json()
    r = ed_c.put(f"/api/grupos/{g['id']}", json={"atualizacao_compartilhada": False})
    assert r.status_code == 409 and r.json()["erro"] == "atualizacao_so_na_criacao"
    r = ed_c.put(f"/api/grupos/{g['id']}", json={"entrada": "livre"})
    assert r.status_code == 422
    # novo dono sem o privilégio (visualizador) é recusado
    v_c, v, _ = usuarios_a.sessao("visualizador")
    ed_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": v["id"]})
    v_c.post(f"/api/grupos/{g['id']}/aceitar")
    r = ed_c.put(f"/api/grupos/{g['id']}", json={"dono_id": v["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "novo_dono_sem_privilegio"
    assert ed_c.delete(f"/api/grupos/{g['id']}").status_code == 204
    # administrativo pelo admin: membro não sai; admin (gerir_todos) remove
    r = sessao_a.post(
        "/api/grupos", json={"nome": _nome(), "administrativo": True, "visibilidade": "inquilino", "entrada": "livre"}
    )
    assert r.status_code == 201
    ga = r.json()
    assert v_c.post(f"/api/grupos/{ga['id']}/entrar").status_code == 200
    r = v_c.delete(f"/api/grupos/{ga['id']}/membros/{v['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "grupo_administrativo"
    assert sessao_a.delete(f"/api/grupos/{ga['id']}/membros/{v['id']}").status_code == 204
    assert sessao_a.delete(f"/api/grupos/{ga['id']}").status_code == 204


def test_convite_a_usuario_de_outro_inquilino_e_404(sessao_a, ids, usuarios_b):
    g = sessao_a.post("/api/grupos", json={"nome": _nome()}).json()
    r = sessao_a.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": ids["b"]["id"]})
    assert r.status_code == 404 and r.json()["erro"] == "usuario_inexistente"
    assert sessao_a.delete(f"/api/grupos/{g['id']}").status_code == 204
