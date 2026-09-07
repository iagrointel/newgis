"""API da camada de desenho do mapa e das anotações de feição (item L2-01-k-desenho-anotacoes).

Cobre o portão de pronto que não depende do navegador: os 7 tipos de desenho gravam e voltam idênticos
(GeoJSON bit a bit), "promover a camada" gera camada com a mesma contagem e geometrias válidas
(ST_IsValid), anotação em feição aparece para outro usuário do MESMO grupo e não para outro inquilino, e a
refutação do item (polígono auto-intersectante, círculo no polo, texto de 10 mil caracteres, 200 cláusulas
não se aplica aqui — é do L2-01-h — mas o equivalente de "entrada hostil sempre 422, nunca 500" vale)."""

import uuid

import pytest

from app.catalogo.documento import gerar_ulid


def _feature(tipo_desenho, geometry, **props):
    return {
        "type": "Feature",
        "id": gerar_ulid(),
        "geometry": geometry,
        "properties": {"tipo_desenho": tipo_desenho, "estilo": {"cor": "#d98a2b", "opacidade": 0.8}, **props},
    }


def _sete_tipos():
    return [
        _feature("ponto", {"type": "Point", "coordinates": [-46.6, -23.5]}),
        _feature("linha", {"type": "LineString", "coordinates": [[-46.6, -23.5], [-46.5, -23.4]]}),
        _feature("poligono", {"type": "Polygon", "coordinates": [[[-46.6, -23.5], [-46.5, -23.5], [-46.5, -23.4], [-46.6, -23.5]]]}),
        _feature("retangulo", {"type": "Polygon", "coordinates": [[[-46.6, -23.5], [-46.55, -23.5], [-46.55, -23.45], [-46.6, -23.45], [-46.6, -23.5]]]}),
        _feature("circulo", {"type": "Point", "coordinates": [-46.6, -23.5]}, raio_m=250.0),
        _feature("texto", {"type": "Point", "coordinates": [-46.6, -23.5]}, texto="anotação de teste"),
        _feature("seta", {"type": "LineString", "coordinates": [[-46.6, -23.5], [-46.59, -23.49]]}),
    ]


@pytest.fixture
def mapa_com_desenho(itens_a):
    features = _sete_tipos()
    it = itens_a.criar("mapa", dados={"esquema_versao": 1, "corpo": {"desenho": {"features": features}}})
    return it, features


def test_sete_tipos_salvam_e_reabrem_identicos(sessao_a, mapa_com_desenho):
    it, features = mapa_com_desenho
    r = sessao_a.get(f"/api/itens/{it['id']}")
    assert r.status_code == 200, r.text
    voltou = r.json()["dados"]["corpo"]["desenho"]["features"]
    assert len(voltou) == 7
    por_id_original = {f["id"]: f for f in features}
    for f in voltou:
        original = por_id_original[f["id"]]
        assert f["geometry"] == original["geometry"]
        assert f["properties"]["tipo_desenho"] == original["properties"]["tipo_desenho"]
        assert f["properties"]["estilo"] == original["properties"]["estilo"]


def test_texto_com_10001_caracteres_e_422(sessao_a, itens_a):
    f = _feature("texto", {"type": "Point", "coordinates": [-46.6, -23.5]}, texto="x" * 10001)
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": "zt desenho texto grande",
              "dados": {"esquema_versao": 1, "corpo": {"desenho": {"features": [f]}}}},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "desenho_invalido"


def test_circulo_no_polo_e_422(sessao_a):
    f = _feature("circulo", {"type": "Point", "coordinates": [-46.6, 89.5]}, raio_m=1000)
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": "zt desenho circulo polo",
              "dados": {"esquema_versao": 1, "corpo": {"desenho": {"features": [f]}}}},
    )
    assert r.status_code == 422, r.text
    detalhe = str(r.json().get("detalhe"))
    assert "circulo_no_polo" in detalhe


def test_poligono_autointersectante_salva_mas_promocao_faz_st_makevalid(sessao_a, itens_a):
    """Borboleta clássica (auto-intersectante); GeoJSON puro aceita, ST_MakeValid decide a forma final."""
    borboleta = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
    }
    f = _feature("poligono", borboleta)
    it = itens_a.criar("mapa", dados={"esquema_versao": 1, "corpo": {"desenho": {"features": [f]}}})
    assert it["dados"]["corpo"]["desenho"]["features"][0]["geometry"] == borboleta
    r = sessao_a.post(f"/api/mapa/{it['id']}/desenho/promover", json={"titulo": "zt camada borboleta"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["n_feicoes"] == 1
    assert j["todas_validas"] is True


def test_teto_de_5001_feicoes_e_422(sessao_a):
    features = [_feature("ponto", {"type": "Point", "coordinates": [0, 0]}) for _ in range(5001)]
    r = sessao_a.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": "zt desenho 5001",
              "dados": {"esquema_versao": 1, "corpo": {"desenho": {"features": features}}}},
    )
    assert r.status_code == 422, r.text


def test_promover_gera_camada_com_mesma_contagem_e_geometrias_validas(sessao_a, mapa_com_desenho):
    it, features = mapa_com_desenho
    r = sessao_a.post(f"/api/mapa/{it['id']}/desenho/promover", json={"titulo": "zt camada promovida sete tipos"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["n_feicoes"] == len(features)
    assert j["todas_validas"] is True
    assert j["geometria"] == "Geometry"  # mistura Point/LineString/Polygon


def test_promover_subconjunto_por_id(sessao_a, mapa_com_desenho):
    it, features = mapa_com_desenho
    ids = [features[0]["id"], features[1]["id"]]
    r = sessao_a.post(f"/api/mapa/{it['id']}/desenho/promover", json={"titulo": "zt camada dois", "ids": ids})
    assert r.status_code == 201, r.text
    assert r.json()["n_feicoes"] == 2


def test_promover_id_inexistente_e_404(sessao_a, mapa_com_desenho):
    it, _features = mapa_com_desenho
    r = sessao_a.post(f"/api/mapa/{it['id']}/desenho/promover", json={"titulo": "zt x", "ids": [gerar_ulid()]})
    assert r.status_code == 404, r.text


def test_promover_sem_desenho_e_422(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = sessao_a.post(f"/api/mapa/{it['id']}/desenho/promover", json={"titulo": "zt vazio"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------------------------- anotações


@pytest.fixture
def grupo_a(sessao_a):
    r = sessao_a.post("/api/grupos", json={"nome": f"zt grupo anotacao {uuid.uuid4().hex[:8]}", "entrada": "livre", "visibilidade": "inquilino"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def camada_a(sessao_a, itens_a):
    it = itens_a.criar("camada_vetorial")
    r = sessao_a.put(f"/api/itens/{it['id']}/compartilhamento", json={"acesso": "inquilino", "grupos": []})
    assert r.status_code == 200, r.text
    return it


def test_anotacao_criar_e_listar(sessao_a, camada_a, grupo_a):
    r = sessao_a.post("/api/anotacoes", json={"camada_id": camada_a["id"], "fid": "42", "grupo_id": grupo_a, "texto": "primeira observação"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["texto"] == "primeira observação"
    assert j["resolvido"] is False
    r = sessao_a.get("/api/anotacoes", params={"camada_id": camada_a["id"], "fid": "42"})
    assert r.status_code == 200, r.text
    assert len(r.json()["anotacoes"]) == 1


def test_anotacao_visivel_a_outro_membro_do_mesmo_grupo(sessao_a, usuarios_a, camada_a, grupo_a):
    """Cria um segundo usuário do inquilino A, ele entra no grupo (entrada 'livre'), e confere que lê a
    anotação criada pelo primeiro — sem ser membro, a mesma consulta devolveria vazio (teste seguinte)."""
    cliente2, _usuario2, _senha2 = usuarios_a.sessao()
    r_criar = sessao_a.post(
        "/api/anotacoes",
        json={"camada_id": camada_a["id"], "fid": "77", "grupo_id": grupo_a, "texto": "visível ao grupo"},
    )
    assert r_criar.status_code == 201, r_criar.text
    r_entrar = cliente2.post(f"/api/grupos/{grupo_a}/entrar")
    assert r_entrar.status_code == 200, r_entrar.text
    assert r_entrar.json()["estado"] == "ativo"
    r3 = cliente2.get("/api/anotacoes", params={"camada_id": camada_a["id"], "fid": "77"})
    assert r3.status_code == 200, r3.text
    corpo = [a for a in r3.json()["anotacoes"] if a["texto"] == "visível ao grupo"]
    assert len(corpo) == 1


def test_anotacao_invisivel_a_usuario_fora_do_grupo(sessao_a, usuarios_a, camada_a, grupo_a):
    """Terceiro usuário do MESMO inquilino, sem entrar no grupo: não vê a anotação (grupo != inquilino)."""
    cliente3, _usuario3, _senha3 = usuarios_a.sessao()
    r_criar = sessao_a.post(
        "/api/anotacoes",
        json={"camada_id": camada_a["id"], "fid": "78", "grupo_id": grupo_a, "texto": "não é para ele"},
    )
    assert r_criar.status_code == 201, r_criar.text
    r3 = cliente3.get("/api/anotacoes", params={"camada_id": camada_a["id"], "fid": "78"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["anotacoes"] == []


def test_anotacao_de_outro_inquilino_e_404(sessao_a, sessao_b, camada_a, grupo_a, itens_b):
    """B não vê a camada de A (RLS de plat.item) nem a anotação, mesmo sabendo os uuids."""
    r = sessao_a.post("/api/anotacoes", json={"camada_id": camada_a["id"], "fid": "9", "grupo_id": grupo_a, "texto": "só de A"})
    assert r.status_code == 201, r.text
    anotacao_id = r.json()["id"]
    r_listar = sessao_b.get("/api/anotacoes", params={"camada_id": camada_a["id"], "fid": "9"})
    assert r_listar.status_code == 404, r_listar.text  # a camada em si já não é legível por B
    r_editar = sessao_b.patch(f"/api/anotacoes/{anotacao_id}", json={"resolvido": True})
    assert r_editar.status_code == 404, r_editar.text
    r_apagar = sessao_b.delete(f"/api/anotacoes/{anotacao_id}")
    assert r_apagar.status_code == 404, r_apagar.text


def test_anotacao_grupo_de_outro_inquilino_e_recusada(sessao_a, sessao_b, camada_a, itens_b):
    grupo_b = sessao_b.post("/api/grupos", json={"nome": f"zt grupo b {uuid.uuid4().hex[:8]}"}).json()["id"]
    r = sessao_a.post("/api/anotacoes", json={"camada_id": camada_a["id"], "fid": "1", "grupo_id": grupo_b, "texto": "cruzado"})
    assert r.status_code == 404, r.text


def test_anotacao_editar_texto_so_autor(sessao_a, usuarios_a, camada_a, grupo_a):
    r = sessao_a.post("/api/anotacoes", json={"camada_id": camada_a["id"], "fid": "5", "grupo_id": grupo_a, "texto": "original"})
    aid = r.json()["id"]
    r2 = sessao_a.patch(f"/api/anotacoes/{aid}", json={"texto": "editado"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["texto"] == "editado"
    assert r2.json()["editado_em"] is not None


def test_anotacao_resolver(sessao_a, camada_a, grupo_a):
    r = sessao_a.post("/api/anotacoes", json={"camada_id": camada_a["id"], "fid": "6", "grupo_id": grupo_a, "texto": "resolver isto"})
    aid = r.json()["id"]
    r2 = sessao_a.patch(f"/api/anotacoes/{aid}", json={"resolvido": True})
    assert r2.status_code == 200, r2.text
    assert r2.json()["resolvido"] is True
    assert r2.json()["resolvido_em"] is not None
