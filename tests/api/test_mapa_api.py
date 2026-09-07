"""API do visualizador de mapa (item L2-01-mapa-web): catálogo de camadas, TileJSON com token cunhado e
repasse de tile do Martin.

Depende da bancada `scripts/mapa_demo_camadas.py criar` (10 camadas no inquilino demo, uma delas com 1
milhão de feições) e do Martin no ar. Sem uma das duas coisas, os testes SALTAM com o motivo dito — nunca
passam por omissão."""

import httpx
import pytest

BANCADA = "(L2-01"          # marca no título das camadas da bancada
MARTIN = "http://127.0.0.1:8151"


def _camadas(sessao):
    r = sessao.get("/api/mapa/camadas")
    assert r.status_code == 200, r.text
    return r.json()["camadas"]


@pytest.fixture(scope="module")
def bancada(sessao_a):
    camadas = [c for c in _camadas(sessao_a) if BANCADA in c["titulo"]]
    if not camadas:
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_camadas.py criar")
    return camadas


@pytest.fixture(scope="module")
def camada_grande(bancada):
    grandes = [c for c in bancada if (c["n_feicoes"] or 0) >= 1_000_000]
    if not grandes:
        pytest.skip("bancada sem a camada de 1 milhão de feições")
    return grandes[0]


@pytest.fixture(scope="module")
def martin_no_ar():
    try:
        httpx.get(f"{MARTIN}/catalog", timeout=5)
    except httpx.HTTPError as e:
        pytest.skip(f"Martin fora do ar em {MARTIN}: {e}")
    return MARTIN


def test_lista_traz_estilo_e_legenda_da_simbologia(camada_grande):
    assert camada_grande["servivel"] is True
    assert camada_grande["familia"] == "Point"
    assert camada_grande["estilo"] and camada_grande["estilo"][0]["type"] == "circle"
    rotulos = [e["rotulo"] for e in camada_grande["legenda"]]
    assert rotulos == ["norte", "sul", "leste", "oeste", "outros"], rotulos


def test_detalhe_traz_extensao_dentro_do_brasil(sessao_a, camada_grande):
    r = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}")
    assert r.status_code == 200, r.text
    oeste, sul, leste, norte = r.json()["extensao"]
    assert -74 < oeste < -30 and -35 < sul < 6 and leste > oeste and norte > sul


def test_camada_de_outro_inquilino_nao_aparece_nem_abre(sessao_b, camada_grande):
    ids = {c["id"] for c in _camadas(sessao_b)}
    assert camada_grande["id"] not in ids
    r = sessao_b.get(f"/api/mapa/camadas/{camada_grande['id']}")
    assert r.status_code == 404, r.text


def test_tilejson_cunha_token_de_uma_camada_so(sessao_a, camada_grande):
    r = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson")
    assert r.status_code == 200, r.text
    tj = r.json()
    assert tj["tilejson"] == "3.0.0"
    assert tj["tiles"] and "token=plat_" in tj["tiles"][0]
    tokens = sessao_a.get("/api/tokens").json()
    meu = [t for t in tokens if t["id"] == tj["token_id"]]
    assert meu and meu[0]["escopos"] == [f"camada:ler:{camada_grande['id']}"], meu


def test_tilejson_novo_revoga_o_anterior_do_mesmo_usuario(sessao_a, camada_grande):
    primeiro = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson").json()
    segundo = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson").json()
    assert primeiro["token_id"] != segundo["token_id"]
    tokens = {t["id"]: t for t in sessao_a.get("/api/tokens").json()}
    assert tokens[primeiro["token_id"]]["revogado_em"] is not None
    assert tokens[segundo["token_id"]]["revogado_em"] is None


def _caminho_do_tile(tj, z, x, y):
    url = tj["tiles"][0]
    caminho = url.split("://", 1)[1].split("/", 1)[1]
    return "/" + caminho.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))


def test_tile_sai_com_token_e_recusa_sem_token(sessao_a, camada_grande, martin_no_ar):
    tj = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson").json()
    com = _caminho_do_tile(tj, 8, 100, 150)
    r = sessao_a.get(com)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    assert r.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    assert len(r.content) > 1000
    sem = com.split("?")[0]
    r2 = sessao_a.get(sem)
    assert r2.status_code == 401, r2.status_code
    assert r2.headers.get("X-Motivo-Recusa") in ("token_ausente", "token_invalido"), dict(r2.headers)


def test_tile_recusa_token_do_outro_inquilino(sessao_a, sessao_b, camada_grande, martin_no_ar):
    """token válido do inquilino B na URL da camada de A: a autorização compara o inquilino DONO do item
    com o inquilino do token (achado do adversário do L2-01-b) — recusa."""
    criado = sessao_b.post("/api/tokens", json={"nome": "zt-mapa-cruzado", "escopos": ["camada:ler"],
                                                "validade_dias": 1})
    assert criado.status_code in (200, 201), criado.text
    valor = criado.json()["token"]
    tj = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson").json()
    caminho = _caminho_do_tile(tj, 8, 100, 150).split("?")[0]
    r = sessao_a.get(f"{caminho}?token={valor}")
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])
    assert r.headers.get("X-Motivo-Recusa") == "tile_de_outro_inquilino", dict(r.headers)
    sessao_b.delete(f"/api/tokens/{criado.json()['id']}")


def test_tile_de_tabela_fora_do_catalogo_e_recusado(sessao_a, martin_no_ar):
    r = sessao_a.get("/tiles/d_demo/t_0000000000000000/8/100/150?token=plat_qualquer")
    assert r.status_code == 401
    assert r.headers.get("X-Motivo-Recusa") == "tabela_nao_catalogada", dict(r.headers)


def test_medidas_de_latencia_do_tile(sessao_a, camada_grande, martin_no_ar, medida):
    """Latência do tile da camada de 1 milhão de feições, frio e quente, pelo repasse da plataforma.

    Frio = primeiro pedido daquele z/x/y (o cache de 64 MB do Martin ainda não tem); quente = o mesmo
    pedido repetido. Mede o caminho INTEIRO (autorização por token + Martin + PostGIS), não só o
    Martin — é o que o navegador sente."""
    import statistics
    import time

    gravar = medida("L2-01-mapa-web")
    tj = sessao_a.get(f"/api/mapa/camadas/{camada_grande['id']}/tilejson").json()

    def pedir(z, x, y):
        t0 = time.perf_counter()
        r = sessao_a.get(_caminho_do_tile(tj, z, x, y))
        assert r.status_code in (200, 204), r.status_code
        return (time.perf_counter() - t0) * 1000, len(r.content)

    frios = []
    for i in range(12):
        ms, _ = pedir(8, 100 + i, 150)
        frios.append(ms)
    quentes = [pedir(8, 100, 150)[0] for _ in range(12)]
    _, bytes_z8 = pedir(8, 100, 150)
    _, bytes_z0 = pedir(0, 0, 0)

    gravar("tile_z8_frio_mediana_ms", round(statistics.median(frios), 1), "ms",
           "12 tiles z8 distintos da camada de 1 mi pelo repasse /tiles (token válido)")
    gravar("tile_z8_quente_mediana_ms", round(statistics.median(quentes), 1), "ms",
           "o MESMO tile z8 pedido 12 vezes (cache em memória do Martin, 64 MB)")
    gravar("tile_z8_bytes", bytes_z8, "bytes", "corpo do tile z8 sem compressão (Accept-Encoding: identity)")
    gravar("tile_z0_bytes", bytes_z0, "bytes",
           "corpo do tile z0 (o milhão inteiro cai neste tile; o corte de 10.000 feições por tile age aqui)")
