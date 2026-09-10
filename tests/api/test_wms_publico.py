"""Item L2-01-a-casca-sig: proxy WMS público (`GET /api/publico/wms/{fonte}`), sem sessão, allowlist fixa.

Sem rede de verdade: `httpx.AsyncClient.get` é trocado por um dublê (monkeypatch) que devolve um PNG de
1x1 — o que se prova aqui é a REGRA (allowlist, REQUEST permitido, repasse do content-type), não a
disponibilidade real do GeoSampa/IBGE/INDE."""

import pytest

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a4944415478da6360000002000155a1a5040000000049454e44ae426082"
)


class _RespostaFalsa:
    def __init__(self, status_code=200, content=PNG_1X1, headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "image/png"}


class _ClienteFalso:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        _ClienteFalso.ultimo_url = url
        _ClienteFalso.ultimo_params = params
        return _RespostaFalsa()


@pytest.fixture
def wms_dublado(monkeypatch):
    import app.mapa.proxy_wms as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _ClienteFalso)
    return mod


def test_fonte_da_lista_devolve_a_imagem(cliente, wms_dublado):
    r = cliente.get("/api/publico/wms/geosampa", params={
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": "MOSAICO_ORTO_RGB_10CM_20CM", "STYLES": "", "CRS": "EPSG:3857",
        "BBOX": "-5200000,-2700000,-5199000,-2699000", "WIDTH": "256", "HEIGHT": "256",
        "FORMAT": "image/png", "TRANSPARENT": "true",
    })
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert r.content == PNG_1X1


def test_fonte_fora_da_allowlist_e_404(cliente, wms_dublado):
    r = cliente.get("/api/publico/wms/nao-existe", params={"REQUEST": "GetMap"})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "fonte_inexistente"


def test_request_fora_da_lista_e_422(cliente, wms_dublado):
    r = cliente.get("/api/publico/wms/ibge", params={"REQUEST": "GetFeatureInfo"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "request_nao_permitido"


def test_sem_request_e_422(cliente, wms_dublado):
    r = cliente.get("/api/publico/wms/inde")
    assert r.status_code == 422, r.text


def test_nao_exige_sessao(cliente, wms_dublado):
    # nenhuma cookie/token nesta chamada — a rota é `x-auth: "-"`, pública mesmo
    r = cliente.get("/api/publico/wms/geosampa", params={"REQUEST": "GetCapabilities"})
    assert r.status_code == 200, r.text
