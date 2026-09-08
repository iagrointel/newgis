"""API da cena 3D (item L2-09-b-cena-extrusao-slides).

Duas superfícies:

* `GET /api/cena/sol` — a posição do Sol que ilumina a cena. Exige sessão ou token como qualquer rota da
  aplicação, recusa instante sem fuso e devolve a luz já no formato do estilo do MapLibre.
* o documento de cena pelas rotas GENÉRICAS do catálogo (`/api/itens`): o tipo `cena` passou a ter esquema
  próprio, então documento fora do esquema é 422 do validador do tipo, e documento inconsistente (slide que
  cita camada que não está na cena, extrusão sem altura) é 422 `cena_invalida` — as duas portas antes de
  gravar, sem rota nova para a cena.
"""

import pytest

from tests.api.conftest import novo_cliente

ULID_A = "01J8ZK3M9Q7V2X5B8N4T6R1C0D"
ULID_B = "01J8ZK3M9Q7V2X5B8N4T6R1C0E"
UUID_A = "11111111-2222-3333-4444-555555555555"
INSTANTE = "2026-06-21T12:00:00-03:00"


def _corpo_cena(**mudancas):
    corpo = {
        "camera": {"centro": [-46.59, -23.49], "zoom": 15.5, "inclinacao": 60, "rotacao": 20},
        "camadas": [{"id": ULID_A, "camada_id": UUID_A, "desenho": "extrusao",
                     "extrusao": {"campo_altura": "altura_m", "escala": 1}}],
        "slides": [{"id": ULID_B, "nome": "vista", "camera": {"centro": [-46.59, -23.49], "zoom": 16},
                    "camadas_visiveis": [ULID_A], "instante": INSTANTE}],
    }
    corpo.update(mudancas)
    return {"esquema_versao": 1, "corpo": corpo}


@pytest.fixture
def cena_criada(sessao_a):
    criadas = []

    def criar(dados, titulo="zt-cena"):
        r = sessao_a.post("/api/itens", json={"tipo": "cena", "titulo": titulo, "dados": dados})
        if r.status_code == 201:
            criadas.append(r.json()["id"])
        return r

    yield criar
    for iid in criadas:
        sessao_a.delete(f"/api/itens/{iid}")


# ---------------------------------------------------------------- posição do Sol
def test_sol_devolve_posicao_e_luz_do_maplibre(sessao_a):
    r = sessao_a.get(f"/api/cena/sol?lat=-23.5505&lon=-46.6333&instante={INSTANTE}")
    assert r.status_code == 200, r.text
    j = r.json()
    # 21 de junho ao meio-dia em São Paulo: Sol ao norte e baixo (verão no hemisfério norte)
    assert 40 < j["elevacao"] < 46, j
    assert j["azimute"] < 30 or j["azimute"] > 330, j
    assert j["instante_utc"] == "2026-06-21T15:00:00Z"
    luz = j["luz"]
    assert luz["anchor"] == "map"
    assert abs(luz["position"][2] - (90 - j["elevacao"])) < 0.01
    assert 0 < luz["intensity"] <= 1


def test_sol_recusa_instante_sem_fuso_e_fora_do_formato(sessao_a):
    r = sessao_a.get("/api/cena/sol?lat=0&lon=0&instante=2026-06-21T12:00:00")
    assert r.status_code == 422 and r.json()["erro"] == "instante_sem_fuso", r.text
    r = sessao_a.get("/api/cena/sol?lat=0&lon=0&instante=ontem")
    assert r.status_code == 422 and r.json()["erro"] == "instante_invalido", r.text


def test_sol_recusa_coordenada_fora_da_faixa(sessao_a):
    r = sessao_a.get(f"/api/cena/sol?lat=120&lon=0&instante={INSTANTE}")
    assert r.status_code == 422, r.text


def test_sol_exige_sessao():
    r = novo_cliente().get(f"/api/cena/sol?lat=0&lon=0&instante={INSTANTE}")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------- documento pelas rotas do catálogo
def test_cena_valida_e_gravada_e_relida(sessao_a, cena_criada):
    r = cena_criada(_corpo_cena())
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    lido = sessao_a.get(f"/api/itens/{iid}")
    assert lido.status_code == 200, lido.text
    corpo = lido.json()["dados"]["corpo"]
    assert corpo["camadas"][0]["extrusao"]["campo_altura"] == "altura_m"
    assert corpo["slides"][0]["camadas_visiveis"] == [ULID_A]


def test_corpo_vazio_continua_aceito(cena_criada):
    assert cena_criada({"esquema_versao": 1, "corpo": {}}).status_code == 201


def test_camera_fora_da_faixa_e_422_do_esquema_do_tipo(cena_criada):
    dados = _corpo_cena()
    dados["corpo"]["camera"]["inclinacao"] = 120
    r = cena_criada(dados)
    assert r.status_code == 422 and r.json()["erro"] == "dados_invalidos", r.text
    assert any("inclinacao" in d["campo"] for d in r.json()["detalhe"]), r.text


def test_slide_que_cita_camada_ausente_e_422_da_cena(cena_criada):
    dados = _corpo_cena()
    dados["corpo"]["slides"][0]["camadas_visiveis"] = [ULID_B]
    r = cena_criada(dados)
    assert r.status_code == 422 and r.json()["erro"] == "cena_invalida", r.text
    assert r.json()["detalhe"][0]["regra"] == "camada_inexistente"


def test_extrusao_sem_altura_e_422_da_cena(cena_criada):
    dados = _corpo_cena()
    dados["corpo"]["camadas"][0]["extrusao"] = {"escala": 1}
    r = cena_criada(dados)
    assert r.status_code == 422 and r.json()["erro"] == "cena_invalida", r.text


def test_edicao_tambem_passa_pelas_duas_validacoes(sessao_a, cena_criada):
    r = cena_criada(_corpo_cena())
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    ruim = _corpo_cena()
    ruim["corpo"]["camadas"][0]["extrusao"] = {"altura_fixa": 5, "base_fixa": 90}
    m = sessao_a.put(f"/api/itens/{iid}", json={"dados": ruim})
    assert m.status_code == 422 and m.json()["erro"] == "cena_invalida", m.text
    bom = _corpo_cena()
    bom["corpo"]["camera"]["zoom"] = 17
    ok = sessao_a.put(f"/api/itens/{iid}", json={"dados": bom})
    assert ok.status_code == 200, ok.text
    assert ok.json()["versao_atual"] >= 2


def test_a_cena_declara_a_camada_como_relacao_do_item(sessao_a, cena_criada):
    """`cena` já estava no extrator de relações do catálogo (app/catalogo/relacoes.py): a camada citada
    no corpo vira relação, e é assim que o "usado por" da camada enxerga a cena."""
    camadas = sessao_a.get("/api/mapa/camadas")
    assert camadas.status_code == 200, camadas.text
    servivel = [c for c in camadas.json()["camadas"] if c["servivel"]]
    if not servivel:
        pytest.skip("sem camada vetorial no inquilino demo para citar na cena")
    alvo = servivel[0]["id"]
    dados = _corpo_cena()
    dados["corpo"]["camadas"][0]["camada_id"] = alvo
    r = cena_criada(dados)
    assert r.status_code == 201, r.text
    usado = sessao_a.get(f"/api/itens/{alvo}/usado-por")
    assert usado.status_code == 200, usado.text
    ids = [x["id"] for x in usado.json()]
    assert r.json()["id"] in ids, usado.text
