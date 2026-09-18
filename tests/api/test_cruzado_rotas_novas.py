"""Par cruzado A→B das rotas que estavam INVISÍVEIS para a varredura (achado de 18/09/2026, item L4-23).

A varredura de `tests/api/test_cruzado.py` monta os casos a partir de `docs/openapi.json`. O arquivo estava
defasado: a aplicação servia 958 operações e o arquivo listava 914, então 51 rotas eram servidas sem que
teste nenhum exercesse a autorização entre inquilinos delas — 22 de escrita, entre elas os quatro DELETE
`/api/webhooks/{id}`, `/api/modelos3d/{id}`, `/api/amc/presets/{id}` e
`/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}`. O arquivo foi regerado; este módulo é a MEDIÇÃO
que faltava.

Cada teste é um PAR, na mesma rodada e sobre o MESMO recurso de B:

1. NEGATIVO — A tenta, nas quatro formas de chamar (sessão de A, token de A com admin:inquilino, sessão de A
   com `X-Plat-Inquilino: demo2`, e sem autenticação nenhuma) e só pode receber 401, 403 ou 404;
2. POSITIVO — B, legítimo, faz a MESMA operação sobre o MESMO recurso e consegue.

O positivo não é enfeite: sem ele, uma rota que recusasse TODO mundo (por defeito de configuração, por
tabela sem GRANT, por um `raise` errado) passaria no negativo e o teste declararia isolamento onde só há
pane. Onde a operação depende de geometria ou de estado que esta camada de teste não monta, o positivo
afirma o que dá para afirmar com honestidade — que B passa da autorização, isto é, NÃO recebe 401/403/404 —
e o docstring do teste diz isso na cara.

Eco do caminho pedido em `instance` (RFC 9457) NÃO é vazamento: o identificador ali é o que o PRÓPRIO
chamador mandou. O que se procura é dado de B na resposta de A — nome, URL, conteúdo, contagem — ou a
existência de B revelada por diferença de resposta.
"""

import base64
import secrets

import pytest

from tests.api.conftest import novo_cliente
from tests.api.ferramentas.apoio_vetor import criar_camada_wkt

pytestmark = pytest.mark.serial

PREFIXO = "zt-cruznovas-"
PADRAO = frozenset({401, 403, 404})
# dado aberto federal (IBGE): passa pela defesa de SSRF da criação de webhook, e não é nome de cliente
URL_WEBHOOK = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"
PRESET_CONTEUDO = {"combinador": "soma_ponderada", "fatores": ["f1", "f2"],
                   "pesos": {"f1": 0.6, "f2": 0.4}}
PNG_1PX = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8"
    "ffff3f0005fe02fea735c8a70000000049454e44ae426082"
)).decode()


def _sufixo() -> str:
    return secrets.token_hex(3)


# ------------------------------------------------------------------ o negativo: as quatro formas de A chamar
def _chamadores(sessao_a, token_a, cliente):
    return (
        ("sessão de A", sessao_a, {}),
        ("token de A (admin:inquilino)", cliente, {"Authorization": f"Bearer {token_a['token']}"}),
        ("sessão de A + X-Plat-Inquilino: demo2", sessao_a, {"X-Plat-Inquilino": "demo2"}),
        ("sem autenticação", cliente, {}),
    )


def negar(sessao_a, token_a, cliente, metodo: str, url: str, corpo=None, marcas=()):
    """A tenta sobre o recurso de B nas quatro formas. Devolve as respostas para quem quiser medir mais."""
    respostas = []
    for nome, cli, headers in _chamadores(sessao_a, token_a, cliente):
        kw = {"headers": headers}
        if corpo is not None:
            kw["json"] = corpo
        r = cli.request(metodo, url, **kw)
        assert r.status_code in PADRAO, (
            f"{metodo} {url} [{nome}] → {r.status_code} (aceitos {sorted(PADRAO)}): {r.text[:300]}"
        )
        for marca in marcas:
            assert marca not in r.text, (
                f"{metodo} {url} [{nome}] devolveu dado de B na resposta: {marca!r} em {r.text[:300]}"
            )
        respostas.append((nome, r))
    return respostas


def passou_da_autorizacao(r, url: str):
    """O positivo mínimo: B não é recusado por autenticação/autorização/inexistência."""
    assert r.status_code not in PADRAO, f"B legítimo foi recusado em {url}: {r.status_code} {r.text[:300]}"


# ------------------------------------------------------------------ recursos de B
@pytest.fixture
def webhook_b(sessao_b):
    s = _sufixo()
    r = sessao_b.post("/api/webhooks", json={"nome": f"{PREFIXO}wh-{s}", "url": URL_WEBHOOK,
                                             "eventos": ["acervo/assinar"]})
    if r.status_code == 403:
        pytest.skip(f"admin de B sem o privilégio org.integracoes nesta base: {r.text[:200]}")
    assert r.status_code == 201, r.text
    w = r.json()
    yield w
    sessao_b.delete(f"/api/webhooks/{w['id']}")


@pytest.fixture
def preset_b(sessao_b):
    s = _sufixo()
    r = sessao_b.post("/api/amc/presets", json={"nome": f"{PREFIXO}preset-{s}", "descricao": "par cruzado",
                                                "escopo": "inquilino", "conteudo": PRESET_CONTEUDO})
    assert r.status_code == 201, r.text
    p = r.json()
    yield p
    sessao_b.delete(f"/api/amc/presets/{p['id']}")


@pytest.fixture
def modelo3d_b(sessao_b):
    """Modelo 3D de B: o arquivo vai por token de serviço (corpo cru), o modelo pela sessão."""
    from tests.apoio_modelos3d import ALTURA_M, LAT, LON, glb_caixa

    s = _sufixo()
    dados = glb_caixa()
    r = sessao_b.post("/api/tokens", json={"nome": f"{PREFIXO}tk-{s}", "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    token = r.json()
    try:
        envio = novo_cliente().post(
            "/api/arquivos?classe=modelo3d", content=dados,
            headers={"Content-Type": "application/octet-stream", "Authorization": f"Bearer {token['token']}"},
        )
        assert envio.status_code == 201, envio.text
        sha = envio.json()["sha256"]
    finally:
        sessao_b.delete(f"/api/tokens/{token['id']}")
    r = sessao_b.post("/api/modelos3d", json={"nome": f"{PREFIXO}m3d-{s}", "origem": "gltf",
                                              "arquivo_sha256": sha, "lon": LON, "lat": LAT,
                                              "altura_m": ALTURA_M})
    assert r.status_code == 201, r.text
    m = r.json()
    yield m
    sessao_b.delete(f"/api/modelos3d/{m['id']}")


def _feicoes(sessao, camada_id: str) -> list[dict]:
    r = sessao.get(f"/api/camadas/{camada_id}/feicoes?limite=10")
    assert r.status_code == 200, r.text
    corpo = r.json()
    return corpo["feicoes"] if isinstance(corpo, dict) and "feicoes" in corpo else corpo["itens"]


@pytest.fixture(scope="module")
def camada_b(env, sessao_b):
    """Camada de linhas de B (LineString: `dividir` só divide linha) com três feições."""
    c = criar_camada_wkt(
        env, sessao_b,
        [{"nome": "L1", "valor": 1, "wkt": "LINESTRING(-46.60 -23.50, -46.58 -23.50)"},
         {"nome": "L2", "valor": 2, "wkt": "LINESTRING(-46.58 -23.50, -46.56 -23.50)"},
         {"nome": "L3", "valor": 3, "wkt": "LINESTRING(-46.60 -23.52, -46.56 -23.52)"}],
        tipo="LineString", slug="demo2", rotulo="cruzado-novas",
    )
    yield c
    sessao_b.delete(f"/api/itens/{c['id']}")


@pytest.fixture
def feicao_b(sessao_b, camada_b):
    return _feicoes(sessao_b, camada_b["id"])[0]


@pytest.fixture
def anexo_b(sessao_b, camada_b, feicao_b):
    url = f"/api/camadas/{camada_b['id']}/feicoes/{feicao_b['id']}/anexos"
    r = sessao_b.post(url, json={"nome": f"{PREFIXO}anexo.png", "content_type": "image/png",
                                 "conteudo": PNG_1PX})
    assert r.status_code == 201, r.text
    a = r.json()
    yield a
    sessao_b.delete(f"{url}/{a['id']}")


# ================================================================== os quatro DELETE (o pior caso)
def test_delete_webhook_de_b(sessao_a, sessao_b, token_a, cliente, webhook_b):
    """A apagar o webhook de B é o pior caso: some a integração do vizinho e não fica rastro para ele."""
    url = f"/api/webhooks/{webhook_b['id']}"
    negar(sessao_a, token_a, cliente, "DELETE", url, marcas=[webhook_b["nome"]])
    assert sessao_b.get(url).status_code == 200, "B perdeu o próprio webhook depois das tentativas de A"
    assert sessao_b.delete(url).status_code == 204, "B legítimo não consegue apagar o próprio webhook"
    assert sessao_b.get(url).status_code == 404


def test_delete_modelo3d_de_b(sessao_a, sessao_b, token_a, cliente, modelo3d_b):
    url = f"/api/modelos3d/{modelo3d_b['id']}"
    negar(sessao_a, token_a, cliente, "DELETE", url, marcas=[modelo3d_b["nome"]])
    assert sessao_b.get(url).status_code == 200, "B perdeu o próprio modelo 3D depois das tentativas de A"
    r = sessao_b.delete(url)
    assert r.status_code == 200, f"B legítimo não consegue apagar o próprio modelo 3D: {r.text[:200]}"
    assert sessao_b.get(url).status_code == 404


def test_delete_preset_amc_de_b(sessao_a, sessao_b, token_a, cliente, preset_b):
    url = f"/api/amc/presets/{preset_b['id']}"
    negar(sessao_a, token_a, cliente, "DELETE", url, marcas=[preset_b["nome"]])
    assert sessao_b.get(url).status_code == 200, "B perdeu o próprio preset depois das tentativas de A"
    assert sessao_b.delete(url).status_code == 204, "B legítimo não consegue apagar o próprio preset"
    assert sessao_b.get(url).status_code == 404


def test_delete_anexo_de_feicao_de_b(sessao_a, sessao_b, token_a, cliente, camada_b, feicao_b, anexo_b):
    url = f"/api/camadas/{camada_b['id']}/feicoes/{feicao_b['id']}/anexos/{anexo_b['id']}"
    negar(sessao_a, token_a, cliente, "DELETE", url, marcas=[anexo_b["nome"]])
    assert sessao_b.get(url).status_code == 200, "B perdeu o próprio anexo depois das tentativas de A"
    assert sessao_b.delete(url).status_code == 204, "B legítimo não consegue apagar o próprio anexo"
    assert sessao_b.get(url).status_code == 404
