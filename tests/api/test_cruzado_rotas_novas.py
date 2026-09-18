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


@pytest.fixture
def desativar_webhook(env):
    """Desativa o webhook de B como o despachante faria (falha repetida), direto na tabela do inquilino."""
    from tests.api.ferramentas.apoio_vetor import _conectar

    def _desativar(webhook_id: str):
        con, _ = _conectar(env, "demo2")
        try:
            with con.cursor() as cur:
                cur.execute("UPDATE plat.webhook SET ativo = false, falhas_consecutivas = 5, "
                            "desativada_em = now(), desativada_motivo = 'teste de par cruzado' "
                            "WHERE id = %s::uuid", (webhook_id,))
            con.commit()
        finally:
            con.close()

    return _desativar


@pytest.fixture
def entrega_b(env, webhook_b):
    """Entrega JÁ FALHADA de B (a entrega nasce do gatilho de despacho; aqui ela é posta direto na tabela,
    no contexto de B, porque o que se mede é a autorização do reenvio, não o despachante)."""
    from tests.api.ferramentas.apoio_vetor import _conectar

    con, _ = _conectar(env, "demo2")
    try:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.webhook_entrega(tenant_id, webhook_id, evento_id, tipo_evento, payload, "
                "estado, tentativas) VALUES (plat.tenant_atual(), %s::uuid, 0, 'acervo/assinar', "
                "%s::jsonb, 'falhou', 3) RETURNING id::text",
                (webhook_b["id"], '{"marca": "' + PREFIXO + 'carga"}'),
            )
            eid = cur.fetchone()["id"]
        con.commit()
    finally:
        con.close()
    return eid


@pytest.fixture
def item_b(sessao_b):
    s = _sufixo()
    r = sessao_b.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO}item-{s}",
                                          "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status_code == 201, r.text
    item = r.json()
    yield item
    sessao_b.delete(f"/api/itens/{item['id']}")


@pytest.fixture
def raster_b(sessao_b):
    s = _sufixo()
    r = sessao_b.post("/api/itens", json={
        "tipo": "raster", "titulo": f"{PREFIXO}raster-{s}",
        "dados": {"colecao": f"{PREFIXO}colecao", "stac_id": f"{PREFIXO}cena-{s}", "perfil": "visual",
                  "origem": "referenciado", "srid_nativo": 4326}})
    if r.status_code != 201:
        pytest.skip(f"não foi possível criar item raster em B nesta base: {r.status_code} {r.text[:200]}")
    item = r.json()
    yield item
    sessao_b.delete(f"/api/itens/{item['id']}")


@pytest.fixture
def rede_b(sessao_b):
    from app.rede_utilidades import instalados

    s = _sufixo()
    r = sessao_b.post("/api/rede", json={"nome": f"{PREFIXO}rede-{s}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rede = r.json()
    r = sessao_b.post(f"/api/rede/{rede['id']}/pacote", content=instalados.bruto("agua-epanet"),
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    r = sessao_b.post(f"/api/rede/{rede['id']}/topologia/habilitar")
    if r.status_code != 201:
        pytest.skip(f"não foi possível habilitar a topologia da rede de B: {r.status_code} {r.text[:200]}")
    yield rede
    sessao_b.delete(f"/api/rede/{rede['id']}")


@pytest.fixture(scope="module")
def metadado_xml() -> str:
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "tests" / "dados" / "inde_iso19139_carta_imagem.xml"
    if not caminho.exists():
        pytest.skip(f"sem o XML ISO de apoio em {caminho}")
    return caminho.read_text(encoding="utf-8")


@pytest.fixture
def feicao_editada_b(sessao_b, camada_b):
    """Feição de B com UMA versão anterior no histórico (é o que a restauração precisa)."""
    alvo = next(f for f in _feicoes(sessao_b, camada_b["id"]) if f["atributos"]["nome"] == "L1")
    r = sessao_b.post(f"/api/camadas/{camada_b['id']}/edicoes", json={
        "atualizar": [{"id": alvo["id"], "versao": alvo["versao"], "atributos": {"valor": 99}}]})
    assert r.status_code == 200, r.text
    h = sessao_b.get(f"/api/camadas/{camada_b['id']}/feicoes/{alvo['id']}/historico")
    assert h.status_code == 200, h.text
    linhas = h.json()
    assert linhas, "a feição de B ficou sem histórico depois da edição"
    return alvo, linhas[0]["id"]


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


# ================================================================== PATCH
def test_patch_webhook_de_b(sessao_a, sessao_b, token_a, cliente, webhook_b):
    url = f"/api/webhooks/{webhook_b['id']}"
    negar(sessao_a, token_a, cliente, "PATCH", url, corpo={"nome": f"{PREFIXO}invadido"},
          marcas=[webhook_b["nome"]])
    depois = sessao_b.get(url)
    assert depois.status_code == 200 and depois.json()["nome"] == webhook_b["nome"], \
        "o nome do webhook de B mudou depois das tentativas de A"
    r = sessao_b.patch(url, json={"nome": f"{PREFIXO}renomeado-por-b"})
    assert r.status_code == 200, f"B legítimo não consegue editar o próprio webhook: {r.text[:200]}"
    assert r.json()["nome"] == f"{PREFIXO}renomeado-por-b"


def test_patch_preset_amc_de_b(sessao_a, sessao_b, token_a, cliente, preset_b):
    url = f"/api/amc/presets/{preset_b['id']}"
    negar(sessao_a, token_a, cliente, "PATCH", url, corpo={"nome": f"{PREFIXO}invadido"},
          marcas=[preset_b["nome"]])
    depois = sessao_b.get(url)
    assert depois.status_code == 200 and depois.json()["nome"] == preset_b["nome"], \
        "o nome do preset de B mudou depois das tentativas de A"
    r = sessao_b.patch(url, json={"nome": f"{PREFIXO}renomeado-por-b"})
    assert r.status_code == 200, f"B legítimo não consegue editar o próprio preset: {r.text[:200]}"


# ================================================================== POST sobre recurso de B
def test_post_rotacionar_segredo_do_webhook_de_b(sessao_a, sessao_b, token_a, cliente, webhook_b):
    """Rotacionar o segredo alheio derruba a assinatura do receptor de B sem que B saiba."""
    url = f"/api/webhooks/{webhook_b['id']}/rotacionar"
    for _nome, r in negar(sessao_a, token_a, cliente, "POST", url, marcas=[webhook_b["nome"]]):
        assert "segredo" not in r.text, f"segredo de webhook na resposta de A: {r.text[:200]}"
    r = sessao_b.post(url)
    assert r.status_code == 200, f"B legítimo não consegue rotacionar o próprio segredo: {r.text[:200]}"
    assert r.json()["segredo"] != webhook_b["segredo"]


def test_post_reativar_webhook_de_b(sessao_a, sessao_b, token_a, cliente, webhook_b, desativar_webhook):
    """B desativa o próprio webhook; A não pode reativá-lo, B pode."""
    desativar_webhook(webhook_b["id"])
    url = f"/api/webhooks/{webhook_b['id']}/reativar"
    negar(sessao_a, token_a, cliente, "POST", url, marcas=[webhook_b["nome"]])
    assert sessao_b.get(f"/api/webhooks/{webhook_b['id']}").json()["ativo"] is False, \
        "o webhook de B foi reativado por A"
    r = sessao_b.post(url)
    assert r.status_code == 200, f"B legítimo não consegue reativar o próprio webhook: {r.text[:200]}"
    assert r.json()["ativo"] is True


def test_post_reenviar_entrega_de_b(sessao_a, sessao_b, token_a, cliente, webhook_b, entrega_b):
    url = f"/api/webhooks/{webhook_b['id']}/entregas/{entrega_b}/reenviar"
    negar(sessao_a, token_a, cliente, "POST", url, marcas=[webhook_b["nome"], PREFIXO + "carga"])
    r = sessao_b.post(url)
    assert r.status_code == 200, f"B legítimo não consegue reenviar a própria entrega: {r.text[:200]}"
    assert r.json()["estado"] == "pendente"


def test_post_aplicar_preset_de_b(sessao_a, sessao_b, token_a, cliente, preset_b):
    url = f"/api/amc/presets/{preset_b['id']}/aplicar"
    corpo = {"ids_fatores": ["f1", "f2"], "fatores": [[10.0, 20.0], [30.0, 40.0]]}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[preset_b["nome"]])
    r = sessao_b.post(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue aplicar o próprio preset: {r.text[:200]}"


def test_post_anexo_em_feicao_de_b(sessao_a, sessao_b, token_a, cliente, camada_b, feicao_b):
    url = f"/api/camadas/{camada_b['id']}/feicoes/{feicao_b['id']}/anexos"
    corpo = {"nome": f"{PREFIXO}de-a.png", "content_type": "image/png", "conteudo": PNG_1PX}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[camada_b["titulo"]])
    antes = sessao_b.get(url)
    assert antes.status_code == 200
    assert all(f"{PREFIXO}de-a.png" != a["nome"] for a in antes.json()), "anexo de A entrou na feição de B"
    r = sessao_b.post(url, json={"nome": f"{PREFIXO}de-b.png", "content_type": "image/png",
                                 "conteudo": PNG_1PX})
    assert r.status_code == 201, f"B legítimo não consegue anexar na própria feição: {r.text[:200]}"
    sessao_b.delete(f"{url}/{r.json()['id']}")


def test_post_restaurar_historico_de_feicao_de_b(sessao_a, sessao_b, token_a, cliente, camada_b,
                                                 feicao_editada_b):
    feicao, historico_id = feicao_editada_b
    url = (f"/api/camadas/{camada_b['id']}/feicoes/{feicao['id']}/historico/{historico_id}/restaurar")
    negar(sessao_a, token_a, cliente, "POST", url, marcas=[camada_b["titulo"]])
    r = sessao_b.post(url)
    assert r.status_code == 200, f"B legítimo não consegue restaurar a própria feição: {r.text[:200]}"
    assert r.json()["sucesso"] is True


def test_post_unir_feicoes_de_b(sessao_a, sessao_b, token_a, cliente, camada_b):
    url = f"/api/camadas/{camada_b['id']}/feicoes/unir"
    alvos = [f for f in _feicoes(sessao_b, camada_b["id"]) if f["atributos"]["nome"] in ("L1", "L2")]
    corpo = {"ids": [f["id"] for f in alvos], "versoes": {f["id"]: f["versao"] for f in alvos}}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[camada_b["titulo"]])
    assert len(_feicoes(sessao_b, camada_b["id"])) == 3, "a camada de B mudou depois das tentativas de A"
    r = sessao_b.post(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue unir as próprias feições: {r.text[:200]}"


def test_post_dividir_feicao_de_b(sessao_a, sessao_b, token_a, cliente, camada_b):
    url = f"/api/camadas/{camada_b['id']}/feicoes/dividir"
    alvo = next(f for f in _feicoes(sessao_b, camada_b["id"]) if f["atributos"]["nome"] == "L3")
    corpo = {"id": alvo["id"], "versao": alvo["versao"], "ponto": [-46.58, -23.52]}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[camada_b["titulo"]])
    r = sessao_b.post(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue dividir a própria feição: {r.text[:200]}"


def test_post_metadado_iso_no_item_de_b(sessao_a, sessao_b, token_a, cliente, item_b, metadado_xml):
    url = f"/api/itens/{item_b['id']}/metadado.xml"
    corpo = {"xml": metadado_xml}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[item_b["titulo"]])
    depois = sessao_b.get(f"/api/itens/{item_b['id']}")
    assert depois.status_code == 200 and depois.json()["titulo"] == item_b["titulo"], \
        "o título do item de B mudou depois das tentativas de A"
    r = sessao_b.post(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue importar metadado no próprio item: {r.text[:200]}"


def test_post_tracar_rede_de_b(sessao_a, sessao_b, token_a, cliente, rede_b):
    url = f"/api/rede/{rede_b['id']}/tracar"
    corpo = {"tipo": "lacos"}
    negar(sessao_a, token_a, cliente, "POST", url, corpo=corpo, marcas=[rede_b["nome"]])
    r = sessao_b.post(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue traçar a própria rede: {r.text[:200]}"


def test_put_ficha_de_imagem_de_b(sessao_a, sessao_b, token_a, cliente, raster_b):
    url = f"/api/imagens/{raster_b['id']}/ficha"
    corpo = {"plataforma": "sentinel-2", "instrumentos": ["msi"], "gsd": 10.0,
             "data_aquisicao": "2026-01-15T13:00:00Z", "fornecedor": "ESA/Copernicus",
             "licenca": "cc-by-4.0", "fonte": "upload",
             "atribuicao": "ESA/Copernicus, CC BY 4.0"}
    negar(sessao_a, token_a, cliente, "PUT", url, corpo=corpo, marcas=[raster_b["titulo"]])
    r = sessao_b.put(url, json=corpo)
    assert r.status_code == 200, f"B legítimo não consegue gravar a ficha da própria imagem: {r.text[:200]}"


# ================================================================== POST de coleção: a escrita de A fica em A
def _nao_atravessa(sessao_a, sessao_b, rota_criar: str, corpo: dict, nome: str, listar: str,
                   campo_nome: str = "nome", apagar: str | None = None):
    """A cria com `X-Plat-Inquilino: demo2` no cabeçalho. Ou a rota recusa, ou o objeto nasce em A — nunca em
    B. O positivo é a criação legítima de B, que continua funcionando."""
    r = sessao_a.post(rota_criar, json=corpo, headers={"X-Plat-Inquilino": "demo2"})
    criado = r.json() if r.status_code < 300 else None
    lista_b = sessao_b.get(listar)
    assert lista_b.status_code == 200
    assert nome not in lista_b.text, f"o que A criou apareceu em B: {nome!r} em {listar}"
    if criado and apagar:
        sessao_a.request("DELETE", apagar.format(id=criado["id"]))
    return r


def test_post_webhook_de_a_nao_nasce_em_b(sessao_a, sessao_b):
    nome = f"{PREFIXO}wh-de-a-{_sufixo()}"
    _nao_atravessa(sessao_a, sessao_b, "/api/webhooks",
                   {"nome": nome, "url": URL_WEBHOOK, "eventos": ["acervo/assinar"]},
                   nome, "/api/webhooks", apagar="/api/webhooks/{id}")
    nome_b = f"{PREFIXO}wh-de-b-{_sufixo()}"
    r = sessao_b.post("/api/webhooks", json={"nome": nome_b, "url": URL_WEBHOOK,
                                             "eventos": ["acervo/assinar"]})
    assert r.status_code == 201, f"B legítimo não consegue criar webhook: {r.text[:200]}"
    sessao_b.delete(f"/api/webhooks/{r.json()['id']}")


def test_post_preset_de_a_nao_nasce_em_b(sessao_a, sessao_b):
    nome = f"{PREFIXO}preset-de-a-{_sufixo()}"
    _nao_atravessa(sessao_a, sessao_b, "/api/amc/presets",
                   {"nome": nome, "escopo": "inquilino", "conteudo": PRESET_CONTEUDO},
                   nome, "/api/amc/presets", apagar="/api/amc/presets/{id}")
    nome_b = f"{PREFIXO}preset-de-b-{_sufixo()}"
    r = sessao_b.post("/api/amc/presets", json={"nome": nome_b, "escopo": "inquilino",
                                                "conteudo": PRESET_CONTEUDO})
    assert r.status_code == 201, f"B legítimo não consegue criar preset: {r.text[:200]}"
    sessao_b.delete(f"/api/amc/presets/{r.json()['id']}")


def test_post_preset_importado_de_a_nao_nasce_em_b(sessao_a, sessao_b):
    nome = f"{PREFIXO}imp-de-a-{_sufixo()}"
    doc = {"formato": "plat/amc_preset", "versao": 1, "nome": nome, "descricao": "",
           "escopo": "inquilino", "conteudo": PRESET_CONTEUDO, "fatores_modelo": None}
    _nao_atravessa(sessao_a, sessao_b, "/api/amc/presets/importar", doc, nome, "/api/amc/presets",
                   apagar="/api/amc/presets/{id}")
    doc_b = {**doc, "nome": f"{PREFIXO}imp-de-b-{_sufixo()}"}
    r = sessao_b.post("/api/amc/presets/importar", json=doc_b)
    assert r.status_code == 201, f"B legítimo não consegue importar preset: {r.text[:200]}"
    sessao_b.delete(f"/api/amc/presets/{r.json()['id']}")


def test_post_modelo3d_de_a_nao_nasce_em_b(sessao_a, sessao_b, modelo3d_b):
    """O sha256 do arquivo é de B. A, mandando o MESMO sha, não pode criar modelo nenhum: o arquivo não é
    dela (404 arquivo_nao_encontrado) — e o modelo de B continua só em B."""
    nome = f"{PREFIXO}m3d-de-a-{_sufixo()}"
    corpo = {"nome": nome, "origem": "gltf", "arquivo_sha256": modelo3d_b["arquivo_sha256"],
             "lon": modelo3d_b["lon"], "lat": modelo3d_b["lat"]}
    r = sessao_a.post("/api/modelos3d", json=corpo)
    assert r.status_code == 404, (
        f"A criou modelo 3D com o sha256 do arquivo de B: {r.status_code} {r.text[:300]}"
    )
    com_cabecalho = sessao_a.post("/api/modelos3d", json=corpo, headers={"X-Plat-Inquilino": "demo2"})
    assert com_cabecalho.status_code == 403, com_cabecalho.text[:300]
    lista_b = sessao_b.get("/api/modelos3d")
    assert lista_b.status_code == 200 and nome not in lista_b.text
    assert sessao_b.get(f"/api/modelos3d/{modelo3d_b['id']}").status_code == 200


def test_post_previsao_de_transformacao_nao_toca_dado_de_ninguem(sessao_a, sessao_b):
    """Rota sem banco: a conta é feita sobre os valores que o chamador manda. Os dois inquilinos recebem a
    MESMA resposta para a MESMA entrada — é a prova de que não há dado de inquilino no meio."""
    corpo = {"valores": [1.0, 2.0, 3.0, 4.0], "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 4},
             "bins": 4}
    ra = sessao_a.post("/api/amc/transformacoes/previsao", json=corpo)
    rb = sessao_b.post("/api/amc/transformacoes/previsao", json=corpo)
    assert ra.status_code == 200, ra.text
    assert rb.status_code == 200, rb.text
    de_a, de_b = ra.json(), rb.json()
    for chave in ("entrada_histograma", "saida_histograma", "n", "n_nulo", "curva"):
        assert de_a[chave] == de_b[chave], f"a previsão diverge entre inquilinos em {chave!r}"


# ================================================================== as 29 rotas de LEITURA invisíveis
# Vazamento de leitura é vazamento igual: é por leitura que se lê o dado do vizinho. As que endereçam um
# recurso de B levam o par completo (A recusada, B lê o próprio); as globais levam a conta que cabe nelas —
# a resposta de A não pode trazer marca de B.
@pytest.fixture(scope="module")
def recursos_de_leitura(env, sessao_b, camada_b):
    """Recursos de B usados só pelas leituras, criados uma vez por módulo."""
    from tests.apoio_modelos3d import ALTURA_M, LAT, LON, glb_caixa

    s = _sufixo()
    criados = []
    r = sessao_b.post("/api/webhooks", json={"nome": f"{PREFIXO}ler-wh-{s}", "url": URL_WEBHOOK,
                                             "eventos": ["acervo/assinar"]})
    assert r.status_code == 201, r.text
    webhook = r.json()
    criados.append(("/api/webhooks/{}", webhook["id"]))
    r = sessao_b.post("/api/amc/presets", json={"nome": f"{PREFIXO}ler-preset-{s}", "escopo": "inquilino",
                                                "conteudo": PRESET_CONTEUDO})
    assert r.status_code == 201, r.text
    preset = r.json()
    criados.append(("/api/amc/presets/{}", preset["id"]))
    r = sessao_b.post("/api/tokens", json={"nome": f"{PREFIXO}ler-tk-{s}", "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    token = r.json()
    try:
        envio = novo_cliente().post(
            "/api/arquivos?classe=modelo3d", content=glb_caixa(),
            headers={"Content-Type": "application/octet-stream", "Authorization": f"Bearer {token['token']}"})
        assert envio.status_code == 201, envio.text
        sha = envio.json()["sha256"]
    finally:
        sessao_b.delete(f"/api/tokens/{token['id']}")
    r = sessao_b.post("/api/modelos3d", json={"nome": f"{PREFIXO}ler-m3d-{s}", "origem": "gltf",
                                              "arquivo_sha256": sha, "lon": LON, "lat": LAT,
                                              "altura_m": ALTURA_M})
    assert r.status_code == 201, r.text
    modelo = r.json()
    criados.append(("/api/modelos3d/{}", modelo["id"]))
    r = sessao_b.post("/api/conexoes", json={"nome": f"{PREFIXO}ler-conexao-{s}", "tipo": "ogc_features",
                                             "url": URL_WEBHOOK})
    conexao = r.json() if r.status_code == 201 else {}
    if conexao:
        criados.append(("/api/conexoes/{}", conexao["id"]))
    r = sessao_b.post("/api/itens", json={
        "tipo": "raster", "titulo": f"{PREFIXO}ler-raster-{s}",
        "dados": {"colecao": f"{PREFIXO}colecao", "stac_id": f"{PREFIXO}cena-{s}", "perfil": "visual",
                  "origem": "referenciado", "srid_nativo": 4326}})
    raster = r.json() if r.status_code == 201 else {}
    if raster:
        criados.append(("/api/itens/{}", raster["id"]))
    feicao = _feicoes(sessao_b, camada_b["id"])[0]
    url_anexos = f"/api/camadas/{camada_b['id']}/feicoes/{feicao['id']}/anexos"
    r = sessao_b.post(url_anexos, json={"nome": f"{PREFIXO}ler-anexo.png", "content_type": "image/png",
                                        "conteudo": PNG_1PX})
    assert r.status_code == 201, r.text
    anexo = r.json()
    yield {"webhook": webhook, "preset": preset, "modelo": modelo, "conexao": conexao, "raster": raster,
           "feicao": feicao, "anexo": anexo, "camada": camada_b}
    sessao_b.delete(f"{url_anexos}/{anexo['id']}")
    for molde, ident in reversed(criados):
        sessao_b.delete(molde.format(ident))


def _leituras(r) -> list[tuple[str, str, bool]]:
    """(rótulo, url, B consegue ler) para cada rota de leitura que aponta um recurso de B."""
    cam, fe = r["camada"]["id"], r["feicao"]["id"]
    itens = [
        ("GET /api/webhooks/{id}", f"/api/webhooks/{r['webhook']['id']}", True),
        ("GET /api/webhooks/{id}/entregas", f"/api/webhooks/{r['webhook']['id']}/entregas", True),
        ("GET /api/amc/presets/{id}", f"/api/amc/presets/{r['preset']['id']}", True),
        ("GET /api/amc/presets/{id}/exportar", f"/api/amc/presets/{r['preset']['id']}/exportar", True),
        ("GET /api/modelos3d/{id}", f"/api/modelos3d/{r['modelo']['id']}", True),
        ("GET /api/modelos3d/{id}/elementos", f"/api/modelos3d/{r['modelo']['id']}/elementos", True),
        # o glb e o 3dtiles só existem depois da conversão (job); para B o 404 é do ARTEFATO, não do modelo
        ("GET /api/modelos3d/{id}/elementos/{guid}", f"/api/modelos3d/{r['modelo']['id']}/elementos/zzz", False),
        ("GET /api/modelos3d/{id}/glb", f"/api/modelos3d/{r['modelo']['id']}/glb", False),
        ("GET /api/modelos3d/{id}/3dtiles/{caminho}", f"/api/modelos3d/{r['modelo']['id']}/3dtiles/tileset.json",
         False),
        ("GET /api/camadas/{id}/feicoes/{globalid}", f"/api/camadas/{cam}/feicoes/{fe}", True),
        ("GET .../feicoes/{globalid}/historico", f"/api/camadas/{cam}/feicoes/{fe}/historico", True),
        ("GET .../feicoes/{globalid}/anexos", f"/api/camadas/{cam}/feicoes/{fe}/anexos", True),
        ("GET .../anexos/{anexo_id}", f"/api/camadas/{cam}/feicoes/{fe}/anexos/{r['anexo']['id']}", True),
        ("GET /api/camadas/{item_id}/classes", f"/api/camadas/{cam}/classes?campo=valor&metodo=quantil&n=3", True),
        ("GET /api/camadas/{item_id}/esquema/campos", f"/api/camadas/{cam}/esquema/campos", True),
    ]
    if r["conexao"]:
        cid = r["conexao"]["id"]
        itens += [
            ("GET /api/conexoes/{id}/colecoes", f"/api/conexoes/{cid}/colecoes", False),
            ("GET /api/conexoes/{id}/colecoes/{colecao}/campos", f"/api/conexoes/{cid}/colecoes/zz/campos", False),
            ("GET /api/conexoes/{id}/colecoes/{colecao}/feicoes", f"/api/conexoes/{cid}/colecoes/zz/feicoes", False),
            ("GET /api/conexoes/{id}/tilejson", f"/api/conexoes/{cid}/tilejson", False),
        ]
    if r["raster"]:
        itens.append(("GET /api/imagens/{item_id}/ficha", f"/api/imagens/{r['raster']['id']}/ficha", True))
    return itens


def test_leituras_sobre_recurso_de_b_nao_vazam(sessao_a, sessao_b, token_a, cliente, recursos_de_leitura):
    """As 20 leituras invisíveis que endereçam um recurso de B, uma a uma, com o par na mesma rodada."""
    r = recursos_de_leitura
    marcas = [r["webhook"]["nome"], r["preset"]["nome"], r["modelo"]["nome"], r["camada"]["titulo"],
              r["anexo"]["nome"], r["webhook"]["url"]]
    marcas += [r["conexao"]["nome"]] if r["conexao"] else []
    marcas += [r["raster"]["titulo"]] if r["raster"] else []
    falhas = []
    for rotulo, url, b_le in _leituras(r):
        try:
            negar(sessao_a, token_a, cliente, "GET", url, marcas=marcas)
        except AssertionError as e:
            falhas.append(f"{rotulo}: {e}")
            continue
        resposta_b = sessao_b.get(url)
        if b_le and resposta_b.status_code != 200:
            falhas.append(f"{rotulo}: B legítimo não lê o próprio recurso ({resposta_b.status_code})")
        if not b_le and resposta_b.status_code in (401, 403):
            falhas.append(f"{rotulo}: B legítimo barrado por autorização ({resposta_b.status_code})")
    assert not falhas, "\n".join(falhas)


def test_leituras_globais_nao_trazem_dado_de_b(sessao_a, sessao_b, recursos_de_leitura):
    """As leituras que não endereçam recurso nenhum (lista do inquilino, tabela da casa, chave de leitura):
    A pode receber 200, mas nunca com marca de B dentro."""
    r = recursos_de_leitura
    marcas = [r["webhook"]["nome"], r["preset"]["nome"], r["modelo"]["nome"], r["webhook"]["url"]]
    falhas = []
    for url in ("/api/webhooks", "/api/amc/presets", "/api/modelos3d", "/api/acervo/frescor/camadas",
                "/api/imagens/formatos", "/api/imagens/licencas", "/api/arquivos/_chave-leitura",
                "/api/arquivos/_cog/autorizar"):
        resposta = sessao_a.get(url)
        if resposta.status_code >= 500:
            falhas.append(f"{url}: {resposta.status_code}")
            continue
        for marca in marcas:
            if marca in resposta.text:
                falhas.append(f"{url}: resposta de A traz {marca!r} (dado de B)")
        assert sessao_b.get(url).status_code < 500, f"{url} quebra para B"
    assert not falhas, "\n".join(falhas)


def test_matriz_de_execucao_amc_de_outro_inquilino(sessao_a, sessao_b, token_a, cliente):
    """`GET /api/amc/execucoes/{id}/matriz`: sem execução AMC pronta nesta base (a grade é job do
    trabalhador), o que se mede é o id que não é de ninguém — tem de dar 404 para A E para B, sem
    diferença de resposta que sirva de oráculo de existência."""
    url = "/api/amc/execucoes/00000000-0000-0000-0000-000000000000/matriz"
    respostas = negar(sessao_a, token_a, cliente, "GET", url)
    de_b = sessao_b.get(url)
    assert de_b.status_code == 404, de_b.text[:200]
    for nome, r in respostas:
        if nome == "sessão de A":
            assert r.status_code == de_b.status_code, (
                f"A e B recebem respostas diferentes para o mesmo id inexistente ({r.status_code} × "
                f"{de_b.status_code}): isso é oráculo de existência")
