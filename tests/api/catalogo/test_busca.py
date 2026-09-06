"""Busca (L0-03-c; ADR 0004 seção 7) sobre o corpus semeado (10 mil em demo): 'municipio' acha 'Município' e
'municpio' (trigram, aproximado); título exato em 1º; tag por API aparece na requisição seguinte; 12 consultas por
campo; id: de item privado de outro → 0; autoritativo antes de comum; facetas batem com count; medidas busca_p95_ms,
busca_trgm_p95_ms, lista_tipo_p95_ms, facetas_p95_ms."""

import statistics
import time

import pytest

from tests.api.catalogo.conftest import titulo_zt
from tests.api.semear_catalogo import PREFIXO, semear
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)

ITEM = "L0-03-catalogo"


@pytest.fixture(scope="module")
def corpus(env):
    import psycopg2
    import psycopg2.extras

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        semear(con, "demo", 10_000)
        semear(con, "demo2", 1_000)
    finally:
        con.close()
    return True


def _p95(f, n=20) -> float:
    tempos = []
    for _ in range(n):
        t0 = time.perf_counter()
        f()
        tempos.append((time.perf_counter() - t0) * 1000)
    tempos.sort()
    return round(tempos[int(0.95 * (n - 1))], 1), round(statistics.median(tempos), 1)


def test_acento_e_trigram_e_titulo_exato(sessao_a, itens_a, corpus, medida):
    exato = itens_a.criar("mapa", titulo="Município")
    r = sessao_a.get("/api/itens?q=municipio&limite=50")
    assert r.status_code == 200 and r.json()["total"] > 1000
    assert r.json()["itens"][0]["id"] == exato["id"], "o título exatamente igual vem em 1º"
    assert all("municíp" in x["titulo"].lower() or "municip" in x["titulo"].lower() for x in r.json()["itens"])
    r2 = sessao_a.get("/api/itens?q=Município&limite=1")
    assert r2.json()["total"] == r.json()["total"]
    r3 = sessao_a.get("/api/itens?q=municpio&limite=10")
    assert r3.status_code == 200 and r3.json().get("aproximado") is True and r3.json()["total"] > 0
    p95, mediana = _p95(lambda: sessao_a.get("/api/itens?q=municipio&limite=50"))
    medida(ITEM)(
        "busca_p95_ms",
        p95,
        "ms",
        "GET /api/itens?q=municipio&limite=50, 20 execuções, corpus 10 mil (mediana %s)" % mediana,
    )
    assert p95 <= 200, p95
    p95t, _ = _p95(lambda: sessao_a.get("/api/itens?q=municpio&limite=50"), n=10)
    medida(ITEM)("busca_trgm_p95_ms", p95t, "ms", "GET /api/itens?q=municpio (trigram de reserva), 10 execuções")


def test_lista_por_tipo_p95(sessao_a, corpus, medida):
    p95, mediana = _p95(lambda: sessao_a.get("/api/itens?tipo=mapa&limite=50"))
    medida(ITEM)(
        "lista_tipo_p95_ms",
        p95,
        "ms",
        "GET /api/itens?tipo=mapa&limite=50, 20 execuções, corpus 10 mil (mediana %s)" % mediana,
    )
    assert p95 < 100, p95
    p95f, _ = _p95(lambda: sessao_a.get("/api/itens/facetas?tipo=mapa"), n=10)
    medida(ITEM)("facetas_p95_ms", p95f, "ms", "GET /api/itens/facetas?tipo=mapa, 10 execuções")


def test_tag_por_api_aparece_na_requisicao_seguinte(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    tag = "zt" + it["id"][:8]
    assert sessao_a.put(f"/api/itens/{it['id']}", json={"tags": [tag]}).status_code == 200
    r = sessao_a.get(f"/api/itens?q=tags:{tag}")
    assert [x["id"] for x in r.json()["itens"]] == [it["id"]]
    r = sessao_a.get(f"/api/itens?tags={tag}")
    assert r.json()["total"] == 1
    assert any(t["tag"] == tag for t in sessao_a.get(f"/api/itens/tags?q={tag[:4]}").json())


def test_doze_consultas_por_campo(sessao_a, itens_a, ids, corpus):
    mapa = itens_a.criar(
        "mapa", titulo=titulo_zt("Rodovia federal"), tags=["zt-campo"], resumo="resumo campo"
    )
    r = sessao_a.post("/api/pastas", json={"nome": titulo_zt("Campo")})
    pasta = r.json()
    sessao_a.post(f"/api/itens/{mapa['id']}/mover", json={"pasta_id": pasta["id"]})
    sessao_a.put(f"/api/itens/{mapa['id']}/compartilhamento", json={"acesso": "inquilino"})
    sessao_a.put(f"/api/itens/{mapa['id']}", json={"status": "obsoleto"})
    login = ids["a"]["login"]
    consultas = {
        "titulo:rodovia zt-campo": 1,
        "tags:zt-campo": 1,
        "resumo:campo tags:zt-campo": 1,
        "descricao:inexistente tags:zt-campo": 0,
        f"dono:{login} tags:zt-campo": 1,
        "tipo:mapa tags:zt-campo": 1,
        "tipo:app tags:zt-campo": 0,
        "status:obsoleto tags:zt-campo": 1,
        "acesso:inquilino tags:zt-campo": 1,
        f"id:{mapa['id']}": 1,
        f"pasta:{pasta['id']}": 1,
        "criado:[2026-01-01 TO *] tags:zt-campo": 1,
        "criado:[* TO 2020] tags:zt-campo": 0,
        "tags:zt-campo NOT tipo:mapa": 0,
        "(tipo:app OR tipo:mapa) tags:zt-campo": 1,
        '"resumo campo" tags:zt-campo': 1,
        "origem:hospedado tags:zt-campo": 1,
        "familia:mapa tags:zt-campo": 1,
    }
    for q, esperado in consultas.items():
        r = sessao_a.get("/api/itens", params={"q": q})
        assert r.status_code == 200, (q, r.text)
        assert r.json()["total"] == esperado, (q, r.json()["total"])
    for q in ("foo:bar", ":x", "id:abc", "tipo:nada", "a " * 201):
        r = sessao_a.get("/api/itens", params={"q": q})
        assert r.status_code == 422, (q, r.text)
    assert sessao_a.get("/api/itens", params={"q": "a & b"}).status_code == 200
    assert sessao_a.get("/api/itens", params={"q": "muni:*"}).status_code == 422  # campo desconhecido, não tsquery


def test_id_de_item_privado_de_outro_usuario_devolve_zero(editor_a, editor2_a, itens_a):
    c1, _ = editor_a
    c2, _ = editor2_a
    it = itens_a.criar("mapa", sessao=c1)
    r = c2.get(f"/api/itens?q=id:{it['id']}")
    assert r.status_code == 200 and r.json()["total"] == 0 and r.json()["itens"] == []
    assert c2.get(f"/api/itens/{it['id']}").status_code == 404
    assert c1.get(f"/api/itens?q=id:{it['id']}").json()["total"] == 1


def test_autoritativo_antes_de_comum_e_obsoleto_depois(sessao_a, itens_a):
    marca = "zt" + titulo_zt()[-6:]
    comum = itens_a.criar("mapa", titulo=f"Hexágono {marca} comum")
    auto = itens_a.criar("mapa", titulo=f"Hexágono {marca} autoritativo")
    obs = itens_a.criar("mapa", titulo=f"Hexágono {marca} obsoleto")
    assert sessao_a.put(f"/api/itens/{auto['id']}", json={"status": "autoritativo"}).status_code == 200
    assert sessao_a.put(f"/api/itens/{obs['id']}", json={"status": "obsoleto"}).status_code == 200
    r = sessao_a.get(f"/api/itens?q=hexagono {marca}")
    ordem = [x["id"] for x in r.json()["itens"]]
    assert ordem.index(auto["id"]) < ordem.index(comum["id"]) < ordem.index(obs["id"]), ordem
    sessao_a.put(f"/api/itens/{auto['id']}", json={"status": "nenhum", "protegido": False})


def test_facetas_batem_com_a_contagem(sessao_a, corpus):
    f = sessao_a.get(f"/api/itens/facetas?q={PREFIXO}").json()
    assert set(f) == {"tipo", "familia", "tags", "dono", "status", "categoria", "acesso"}
    for faceta in f["tipo"]:
        n = sessao_a.get(f"/api/itens?q={PREFIXO}&tipo={faceta['valor']}&limite=1").json()["total"]
        assert n == faceta["n"], faceta
    for faceta in f["acesso"]:
        n = sessao_a.get(f"/api/itens?q={PREFIXO}&acesso={faceta['valor']}&limite=1").json()["total"]
        assert n == faceta["n"], faceta
    # status: a faceta conta o NULL como 'nenhum'; o filtro ?status=nenhum tem de devolver a MESMA contagem
    # (achado do frontend: comparação por ANY dava 0 porque o valor está gravado como NULL)
    for faceta in f["status"]:
        n = sessao_a.get(f"/api/itens?q={PREFIXO}&status={faceta['valor']}&limite=1").json()["total"]
        assert n == faceta["n"], faceta
    assert sessao_a.get(f"/api/itens?q={PREFIXO}&status=inventado").status_code == 422
    # dono: a faceta traz o id porque o filtro lateral é ?dono_id=<int> (achado do frontend)
    for faceta in f["dono"]:
        assert isinstance(faceta["id"], int) and faceta["valor"] and "rotulo" in faceta
        n = sessao_a.get(f"/api/itens?q={PREFIXO}&dono_id={faceta['id']}&limite=1").json()["total"]
        assert n == faceta["n"], faceta


def test_filtros_laterais_bbox_data_favoritos_meus(sessao_a, itens_a, corpus):
    it = itens_a.criar("mapa", extent=[-45.5, -23.5, -45.4, -23.4])
    r = sessao_a.get("/api/itens?bbox=-46,-24,-45,-23&q=id:" + it["id"])
    assert r.json()["total"] == 1
    assert sessao_a.get("/api/itens?bbox=-46,-24,-45,-23&q=id:" + it["id"] + "&tipo=app").json()["total"] == 0
    assert sessao_a.get("/api/itens?bbox=1,2,3").status_code == 422
    sessao_a.put(f"/api/favoritos/{it['id']}")
    assert any(x["id"] == it["id"] for x in sessao_a.get("/api/itens?favoritos=true&limite=200").json()["itens"])
    assert sessao_a.get(f"/api/itens?meus=true&q=id:{it['id']}").json()["total"] == 1
    assert sessao_a.get("/api/itens?modificado_de=2099-01-01").json()["total"] == 0
    r = sessao_a.get("/api/itens?q=municipio&prefixo=true&limite=1")  # prefixo ao vivo não quebra
    assert r.status_code == 200
    r = sessao_a.get("/api/itens?q=munic&prefixo=true&limite=1")
    assert r.status_code == 200 and r.json()["total"] > 0
