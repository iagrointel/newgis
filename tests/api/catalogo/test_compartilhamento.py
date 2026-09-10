"""Compartilhamento (L0-03-e; ADR 0004 seção 6): privado → grupo → inquilino → link; membro vê, não-membro 404;
link 200 anônimo → revogar → 404 em ≤ 1 s (medido) → 20 clientes simultâneos 0 × 200; expirado 410; token 64 hex;
publico com o inquilino desligado 400; item de outro com o próprio grupo 404; elevar dependência de outro dono 403;
contagem de acessos; superadmin lendo outro inquilino não vê item privado."""

import concurrent.futures
import datetime
import secrets
import time

from tests.api.catalogo.conftest import documento_mapa, titulo_zt
from tests.api.conftest import novo_cliente

ITEM = "L0-03-catalogo"


def test_niveis_e_grupo(sessao_a, itens_a, editor_a, editor2_a, visualizador_a, usuarios_a):
    dono_c, dono = editor_a
    membro_c, membro = editor2_a
    fora_c, fora = visualizador_a
    it = itens_a.criar("mapa", sessao=dono_c)
    iid = it["id"]
    assert membro_c.get(f"/api/itens/{iid}").status_code == 404 and fora_c.get(f"/api/itens/{iid}").status_code == 404
    r = dono_c.post("/api/grupos", json={"nome": titulo_zt("grupo"), "entrada": "convite"})
    g = r.json()
    assert dono_c.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": membro["id"]}).status_code == 201
    assert membro_c.post(f"/api/grupos/{g['id']}/aceitar").status_code == 200
    r = dono_c.put(f"/api/itens/{iid}/compartilhamento", json={"grupos": [g["id"]]})
    assert r.status_code == 200 and [x["id"] for x in r.json()["grupos"]] == [g["id"]], r.text
    assert membro_c.get(f"/api/itens/{iid}").status_code == 200
    assert fora_c.get(f"/api/itens/{iid}").status_code == 404
    assert membro_c.get(f"/api/itens/{iid}").json()["pode_editar"] is False
    assert membro_c.put(f"/api/itens/{iid}", json={"titulo": "x"}).status_code == 403
    assert membro_c.get(f"/api/itens?grupo_id={g['id']}").json()["total"] == 1
    # compartilhar item de outro com o próprio grupo: membro não edita o item → 403 (lê mas não compartilha)
    r = membro_c.put(f"/api/itens/{iid}/compartilhamento", json={"grupos": []})
    assert r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item"
    # grupo em que o dono não contribui: 403 sem_contribuicao_no_grupo
    r = membro_c.post(
        "/api/grupos", json={"nome": titulo_zt("g2"), "contribuicao": "dono_gerentes", "visibilidade": "inquilino"}
    )
    g2 = r.json()
    assert membro_c.post(f"/api/grupos/{g2['id']}/membros", json={"usuario_id": dono["id"]}).status_code == 201
    assert dono_c.post(f"/api/grupos/{g2['id']}/aceitar").status_code == 200
    r = dono_c.put(f"/api/itens/{iid}/compartilhamento", json={"grupos": [g["id"], g2["id"]]})
    assert r.status_code == 403 and r.json()["erro"] == "sem_contribuicao_no_grupo", r.text
    # inquilino
    r = dono_c.put(f"/api/itens/{iid}/compartilhamento", json={"acesso": "inquilino"})
    assert r.status_code == 200 and r.json()["acesso"] == "inquilino"
    assert fora_c.get(f"/api/itens/{iid}").status_code == 200
    assert fora_c.get(f"/api/itens/{iid}/compartilhamento").json()["links"] == []  # sem edição, sem detalhe
    # público: o privilégio vem antes da configuração do inquilino. Editor não tem compartilhar.publico (só admin,
    # migração 003) → 403; o admin, com o inquilino sem compartilhar_publico ligado → 400 publico_desligado.
    it2 = itens_a.criar("mapa", sessao=dono_c)
    r = dono_c.put(f"/api/itens/{it2['id']}/compartilhamento", json={"acesso": "publico"})
    assert r.status_code == 403 and r.json()["erro"] == "sem_permissao", r.text
    it3 = itens_a.criar("mapa")
    r = sessao_a.put(f"/api/itens/{it3['id']}/compartilhamento", json={"acesso": "publico"})
    assert r.status_code == 400 and r.json()["erro"] == "publico_desligado", r.text
    assert sessao_a.get(f"/api/itens/{iid}").json()["compartilhado_com_grupos"] == 1
    # apagar o grupo remove o compartilhamento; o item continua
    assert dono_c.delete(f"/api/grupos/{g['id']}").status_code == 204
    assert sessao_a.get(f"/api/itens/{iid}").json()["compartilhado_com_grupos"] == 0


def test_link_anonimo_revogacao_e_expiracao(sessao_a, itens_a, medida):
    it = itens_a.criar("mapa", resumo="por link")
    iid = it["id"]
    r = sessao_a.post(f"/api/itens/{iid}/links", json={"nome": "zt link"})
    assert r.status_code == 201, r.text
    j = r.json()
    tok = j["token"]
    assert len(tok) == 64 and all(c in "0123456789abcdef" for c in tok) and j["url"].endswith(f"/c/{tok}")
    anon = novo_cliente()
    r = anon.get(f"/api/compartilhado/{tok}")
    assert r.status_code == 200 and r.json()["item"]["id"] == iid and r.headers["cache-control"].startswith("no-store")
    assert "login" not in r.json()["item"]["dono"] and "pode_editar" not in r.json()["item"]
    assert anon.get(f"/api/compartilhado/{tok}/itens/{iid}").status_code == 200
    assert anon.get(f"/api/compartilhado/{tok}/itens/{iid}/miniatura").status_code == 204
    outro = itens_a.criar("mapa")
    assert anon.get(f"/api/compartilhado/{tok}/itens/{outro['id']}").status_code == 404  # fora do link
    links = sessao_a.get(f"/api/itens/{iid}/links").json()
    assert links[0]["acessos"] == 3 and links[0]["prefixo"] == tok[:8]
    assert anon.get(f"/api/compartilhado/{secrets.token_hex(32)}").status_code == 404
    assert anon.get(f"/api/compartilhado/{tok[:16]}").status_code == 404
    # revogar: 404 em ≤ 1 s, e 20 clientes simultâneos depois = 0 × 200
    t0 = time.perf_counter()
    assert sessao_a.delete(f"/api/itens/{iid}/links/{j['id']}").status_code == 204
    r = anon.get(f"/api/compartilhado/{tok}")
    dt = (time.perf_counter() - t0) * 1000
    assert r.status_code == 404 and r.json()["erro"] == "link_invalido"
    medida(ITEM)("revogacao_nega_ms", round(dt, 1), "ms", "DELETE link + GET /api/compartilhado/<token> → 404")
    assert dt <= 1000
    with concurrent.futures.ThreadPoolExecutor(20) as ex:
        codigos = list(ex.map(lambda _: novo_cliente().get(f"/api/compartilhado/{tok}").status_code, range(20)))
    assert codigos.count(200) == 0 and set(codigos) == {404}
    assert sessao_a.delete(f"/api/itens/{iid}/links/{j['id']}").status_code == 204  # idempotente
    # expirado = 410
    exp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = sessao_a.post(f"/api/itens/{iid}/links", json={"expira_em": exp})
    tok2 = r.json()["token"]
    assert anon.get(f"/api/compartilhado/{tok2}").status_code == 200
    time.sleep(2.2)
    r = anon.get(f"/api/compartilhado/{tok2}")
    assert r.status_code == 410 and r.json()["erro"] == "link_expirado"
    exp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = sessao_a.post(f"/api/itens/{iid}/links", json={"expira_em": exp})
    assert r.status_code == 400 and r.json()["erro"] == "validade_acima_do_maximo"
    # link de item na lixeira não resolve
    r = sessao_a.post(f"/api/itens/{iid}/links", json={})
    tok3 = r.json()["token"]
    assert sessao_a.delete(f"/api/itens/{iid}").status_code == 204
    assert anon.get(f"/api/compartilhado/{tok3}").status_code == 404
    assert sessao_a.post(f"/api/lixeira/{iid}/restaurar").status_code == 200
    assert anon.get(f"/api/compartilhado/{tok3}").status_code == 200


def test_link_com_dependencias_e_elevar_de_outro_dono(sessao_a, itens_a, editor_a):
    dono_c, _ = editor_a
    camada_do_editor = itens_a.criar("camada_vetorial", sessao=dono_c)
    minha_camada = itens_a.criar("camada_vetorial")
    sessao_a_sem_edit = novo_cliente()
    # o admin tem editar_tudo; use um segundo editor sem acesso à camada do primeiro
    mapa = itens_a.criar("mapa", dados=documento_mapa(minha_camada["id"]))
    r = sessao_a.get(f"/api/itens/{mapa['id']}/compartilhamento")
    deps = r.json()["dependencias"]
    assert [d["id"] for d in deps] == [minha_camada["id"]] and deps[0]["pode_editar"] is True
    r = sessao_a.post(f"/api/itens/{mapa['id']}/links", json={"itens_incluidos": [minha_camada["id"]]})
    assert r.status_code == 201 and r.json()["itens_incluidos"] == [minha_camada["id"]]
    tok = r.json()["token"]
    anon = novo_cliente()
    j = anon.get(f"/api/compartilhado/{tok}").json()
    assert [x["id"] for x in j["itens_incluidos"]] == [minha_camada["id"]]
    assert anon.get(f"/api/compartilhado/{tok}/itens/{minha_camada['id']}").status_code == 200
    # editor: mapa com a camada de outro (visível por inquilino), elevar = 403
    sessao_a.put(f"/api/itens/{minha_camada['id']}/compartilhamento", json={"acesso": "inquilino"})
    mapa2 = itens_a.criar(
        "mapa", sessao=dono_c, dados=documento_mapa(minha_camada["id"])
    )
    r = dono_c.post(f"/api/itens/{mapa2['id']}/links", json={"itens_incluidos": [minha_camada["id"]]})
    assert (
        r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item" and minha_camada["id"] in r.json()["detalhe"]
    )
    r = dono_c.put(
        f"/api/itens/{mapa2['id']}/compartilhamento",
        json={"acesso": "inquilino", "aplicar_a_dependencias": [minha_camada["id"]]},
    )
    assert r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item"
    del sessao_a_sem_edit, camada_do_editor


def test_publico_so_com_inquilino_autorizando(sessao_plat, sessao_a, itens_a):
    it = itens_a.criar("mapa")
    anon = novo_cliente()
    assert anon.get(f"/api/publico/itens/{it['id']}").status_code == 404
    r = sessao_a.put(f"/api/itens/{it['id']}/compartilhamento", json={"acesso": "publico"})
    assert r.status_code == 400 and r.json()["erro"] == "publico_desligado"


def test_superadmin_lendo_outro_inquilino_nao_ve_privado(sessao_plat, itens_a, sessao_a):
    it = itens_a.criar("mapa")
    r = sessao_plat.get(f"/api/itens/{it['id']}", headers={"X-Plat-Inquilino": "demo"})
    assert r.status_code == 400  # a rota de leitura não aceita o cabeçalho (só DELETE, para o caso forçado)
    r = sessao_plat.get(f"/api/itens/{it['id']}")
    assert r.status_code == 404
