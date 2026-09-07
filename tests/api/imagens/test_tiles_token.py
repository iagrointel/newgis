"""Portão do item L1-02-tiles-token, cláusula por cláusula, e as refutações do adversário.

O que este arquivo mede em processo (TestClient): as URLs do contrato C6, a validade do
GetCapabilities do WMTS contra o ESQUEMA OFICIAL do OGC (cópia em tests/dados/ogc_xsd), a expressão
NDVI por parâmetro, o registro com contagem por token e as recusas (token de outro inquilino, token
revogado, Referer falso, escopo insuficiente, tentativa de mandar endereço de arquivo).

O que NÃO cabe aqui e está em `scripts/bench_tiles.py`: taxa de ladrilhos por segundo com o cache do
nginx, `proxy_cache_lock` e o tempo entre revogar e receber 403 — as três exigem o nginx à frente da
aplicação, e o número medido está em `tests/medidas/L1-02-tiles-token.json`."""

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
XSD = ROOT / "tests" / "dados" / "ogc_xsd"
Z, X, Y = 12, 1503, 2230  # ladrilho que cobre o raster de teste (Brasília)


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    """Um COG de verdade (4 bandas, 16 bits) no balde do inquilino A, com item STAC e espelho."""
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def token_tiles(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_tiles_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": "zt-tiles-b", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


# ---------------------------------------------------------------- cláusula: URLs XYZ e TileJSON
def test_xyz_devolve_png_com_e_sem_extensao(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    sem = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}")
    com = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    assert sem.status_code == 200 and sem.headers["content-type"] == "image/png"
    assert sem.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert com.status_code == 200 and com.content[:4] == b"\x89PNG"
    jpg = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.jpg")
    assert jpg.status_code == 200 and jpg.content[:3] == b"\xff\xd8\xff"


def test_ladrilho_fora_da_cobertura_devolve_204(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/{Z}/0/0.png")
    assert r.status_code == 204 and not r.content


def test_tilejson_aponta_para_a_propria_url_com_token(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/tilejson.json")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tilejson"] == "3.0.0" and len(corpo["tiles"]) == 1
    # desde o item L7-26-cdn-tiles o TileJSON aponta para o endereço VERSIONADO ("item@sha256"), que é
    # o que deixa a CDN guardar o ladrilho para sempre (ver test_cdn_tiles.py para a cláusula do cache).
    assert f"/svc/{tok}/raster/{item}@" in corpo["tiles"][0]
    assert corpo["tiles"][0].endswith("{z}/{x}/{y}.png")
    assert corpo["minzoom"] <= corpo["maxzoom"] and len(corpo["bounds"]) == 4


# ---------------------------------------------------------------- cláusula: WMTS válido no esquema OGC
def _validar_xsd(xml_texto: str, tmp_path: Path) -> subprocess.CompletedProcess:
    arq = tmp_path / "capabilities.xml"
    arq.write_text(xml_texto, encoding="utf-8")
    return subprocess.run(
        ["xmllint", "--nonet", "--noout", "--schema",
         str(XSD / "wmts" / "1.0" / "wmtsGetCapabilities_response.xsd"), str(arq)],
        capture_output=True, text=True, cwd=str(XSD),
        env={**os.environ, "XML_CATALOG_FILES": str(XSD / "catalogo.xml")},
    )


@pytest.mark.skipif(shutil.which("xmllint") is None, reason="xmllint (libxml2-utils) ausente")
def test_wmts_getcapabilities_valida_no_esquema_oficial(token_tiles, raster_demo, tmp_path):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    for url in (f"/svc/{tok}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml",
                f"/svc/{tok}/raster/{item}/wmts?SERVICE=WMTS&REQUEST=GetCapabilities&VERSION=1.0.0"):
        r = c.get(url)
        assert r.status_code == 200, (url, r.text[:300])
        assert r.headers["content-type"].startswith("application/xml")
        saida = _validar_xsd(r.text, tmp_path)
        assert saida.returncode == 0, saida.stderr[-2000:]
        assert "validates" in saida.stderr


def test_wmts_gettile_kvp_serve_o_mesmo_ladrilho_do_xyz(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    xyz = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    kvp = c.get(f"/svc/{tok}/raster/{item}/wmts", params={
        "SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0", "LAYER": item,
        "STYLE": "default", "TILEMATRIXSET": "WebMercatorQuad", "TILEMATRIX": str(Z),
        "TILEROW": str(Y), "TILECOL": str(X), "FORMAT": "image/png"})
    assert kvp.status_code == 200 and kvp.content == xyz.content


def test_wmts_recusa_grade_e_camada_que_nao_sao_as_dele(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    base = {"SERVICE": "WMTS", "REQUEST": "GetTile", "TILEMATRIX": str(Z), "TILEROW": str(Y),
            "TILECOL": str(X), "FORMAT": "image/png"}
    r = c.get(f"/svc/{tok}/raster/{item}/wmts", params={**base, "TILEMATRIXSET": "EPSG:4326"})
    assert r.status_code == 422 and r.json()["erro"] == "grade_invalida"
    r = c.get(f"/svc/{tok}/raster/{item}/wmts", params={**base, "LAYER": "outra"})
    assert r.status_code == 422 and r.json()["erro"] == "camada_invalida"


def test_capabilities_declara_o_gabarito_rest_com_o_token(token_tiles, raster_demo):
    """O que o QGIS guarda no projeto é o `ResourceURL`: ele TEM de trazer o token, senão a camada
    salva não volta a abrir amanhã."""
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    xml = c.get(f"/svc/{tok}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml").text
    assert f"/svc/{tok}/raster/{item}/{{TileMatrix}}/{{TileCol}}/{{TileRow}}.png" in xml
    assert "WellKnownScaleSet>urn:ogc:def:wkss:OGC:1.0:GoogleMapsCompatible" in xml


# ---------------------------------------------------------------- cláusula: expressão NDVI por parâmetro
def test_ndvi_por_parametro_muda_o_ladrilho(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    rgb = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png", params={"bandas": "3,2,1", "faixa": "0,4000"})
    ndvi = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png",
                 params={"expressao": "(b4-b3)/(b4+b3)", "faixa": "-1,1", "colormap": "viridis"})
    assert rgb.status_code == 200 and ndvi.status_code == 200
    assert ndvi.content[:4] == b"\x89PNG" and ndvi.content != rgb.content


def test_ndvi_no_wmts_e_no_tilejson_carrega_a_expressao(token_tiles, raster_demo):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    p = {"expressao": "(b4-b3)/(b4+b3)", "faixa": "-1,1", "colormap": "viridis"}
    tj = c.get(f"/svc/{tok}/raster/{item}/tilejson.json", params=p).json()
    assert "expressao=" in tj["tiles"][0] and "colormap=viridis" in tj["tiles"][0]
    xml = c.get(f"/svc/{tok}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml", params=p).text
    assert "expressao=" in xml and "colormap=viridis" in xml


@pytest.mark.parametrize("expressao", [
    "__import__('os').system('id')", "eval(b1)", "b1; import os", "open('/etc/passwd')",
    "b1 if __import__ else b2", "getattr(b1,'x')", "b" + "1" * 300,
])
def test_expressao_fora_da_gramatica_e_recusada(token_tiles, raster_demo, expressao):
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png", params={"expressao": expressao})
    assert r.status_code in (422, 400), (expressao, r.status_code, r.text[:200])


def test_expressao_sem_banda_e_recusada(token_tiles, raster_demo):
    from app.imagens import tiles

    assert tiles.expressao_valida("1+1")[0] is False
    assert tiles.expressao_valida("(b4-b3)/(b4+b3)")[0] is True
    assert tiles.expressao_valida("where(b1>0,b1,0)")[0] is True


# ---------------------------------------------------------------- refutação: SSRF, inquilino, referer
def test_nao_existe_parametro_de_endereco_de_arquivo(token_tiles, raster_demo):
    """A refutação do item fala em 'URL arbitrária no parâmetro'. A resposta desta implementação é
    estrutural: NENHUMA rota do serviço tem parâmetro de endereço — o caminho do COG vem do catálogo.
    O teste prova que mandar `url=` não muda nada (é parâmetro ignorado) e que o OpenAPI não declara
    nenhum parâmetro de endereço nas rotas /svc/.../raster."""
    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    limpo = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
    com_url = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png",
                    params={"url": "http://169.254.169.254/latest/meta-data/"})
    assert com_url.status_code == 200 and com_url.content == limpo.content

    from app.main import app

    spec = app.openapi()
    for caminho, metodos in spec["paths"].items():
        if not caminho.startswith("/svc/{token}/raster"):
            continue
        for op in metodos.values():
            nomes = {p["name"].lower() for p in op.get("parameters", [])}
            assert not (nomes & {"url", "src", "href", "arquivo", "caminho", "endereco"}), (caminho, nomes)


def test_token_de_outro_inquilino_nao_ve_o_item(token_tiles_b, raster_demo):
    c, tok_b, item = _cliente(), token_tiles_b["token"], raster_demo["item_id"]
    for url in (f"/svc/{tok_b}/raster/{item}/{Z}/{X}/{Y}.png",
                f"/svc/{tok_b}/raster/{item}/tilejson.json",
                f"/svc/{tok_b}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml"):
        r = c.get(url)
        assert r.status_code == 403, (url, r.status_code)
        assert r.json()["erro"] == "item_indisponivel"


def test_autorizacao_do_nginx_tambem_recusa_item_de_outro_inquilino(token_tiles, token_tiles_b, raster_demo):
    """A subrequisição do `auth_request` é o ÚNICO ponto que roda quando o ladrilho já está no cache do
    nginx (a chave de cache não tem o token). Se ela não conferisse o dono do item, um token válido de
    outro inquilino receberia o ladrilho alheio — foi o que aconteceu na bancada de 07/09 antes do
    conserto."""
    c, item = _cliente(), raster_demo["item_id"]
    ok = c.get("/api/tiles/autorizar",
               headers={"X-Plat-Token": token_tiles["token"], "X-Plat-Item": item, "X-Plat-Tipo": "raster"})
    assert ok.status_code == 204
    nao = c.get("/api/tiles/autorizar",
                headers={"X-Plat-Token": token_tiles_b["token"], "X-Plat-Item": item, "X-Plat-Tipo": "raster"})
    assert nao.status_code == 403


def test_token_inexistente_e_malformado_dao_403(raster_demo):
    c, item = _cliente(), raster_demo["item_id"]
    for tok in ("plat_" + "a" * 43, "sem-prefixo", "plat_curto"):
        r = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
        assert r.status_code == 403, (tok, r.status_code)


def test_escopo_insuficiente_da_403(sessao_a, raster_demo):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-sem-escopo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201
    tok, tid = r.json()["token"], r.json()["id"]
    try:
        c = _cliente()
        resp = c.get(f"/svc/{tok}/raster/{raster_demo['item_id']}/{Z}/{X}/{Y}.png")
        assert resp.status_code == 403 and resp.json()["erro"] == "escopo_insuficiente"
    finally:
        sessao_a.delete(f"/api/tokens/{tid}")


def test_restricao_de_referer_e_de_ip(sessao_a, raster_demo):
    """Token restrito a uma origem: sem Referer/Origin, e com Referer de outro domínio, recusa."""
    item = raster_demo["item_id"]
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-referer", "escopos": ["tiles:ler"],
                                           "restricao": {"referer": ["https://mapa.exemplo.gov.br"]}})
    assert r.status_code == 201, r.text
    tok, tid = r.json()["token"], r.json()["id"]
    try:
        c = _cliente()
        url = f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png"
        assert c.get(url).status_code == 403
        assert c.get(url, headers={"Referer": "https://outro.exemplo.com/mapa"}).status_code == 403
        ok = c.get(url, headers={"Referer": "https://mapa.exemplo.gov.br/mapa"})
        assert ok.status_code == 200, ok.text[:200]
    finally:
        sessao_a.delete(f"/api/tokens/{tid}")


def test_restricao_de_ip_recusa_fora_da_faixa(sessao_a, raster_demo):
    """A restrição por IP é a mesma função do resto da API (`_checar_restricao`): o cliente de teste
    não tem endereço roteável, então o token restrito a uma faixa recusa — que é o comportamento
    pedido (fora da faixa, 403). A faixa que ACEITA é exercida na bancada, contra o nginx."""
    item = raster_demo["item_id"]
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-ip", "escopos": ["tiles:ler"],
                                           "restricao": {"ip": ["10.0.0.0/8"]}})
    assert r.status_code == 201, r.text
    tok, tid = r.json()["token"], r.json()["id"]
    try:
        c = _cliente()
        resp = c.get(f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png")
        assert resp.status_code == 403 and resp.json()["erro"] == "ip_nao_permitido"
    finally:
        sessao_a.delete(f"/api/tokens/{tid}")


def test_token_revogado_para_de_servir(sessao_a, raster_demo):
    """Em processo, sem os caches do nginx: revogar tem efeito na PRIMEIRA leitura depois de o cache de
    autorização da aplicação vencer (2 s). O tempo medido ponta a ponta, com nginx, está na medida."""
    import time

    from app.imagens import rotas_tiles

    item = raster_demo["item_id"]
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-revoga", "escopos": ["tiles:ler"]})
    tok, tid = r.json()["token"], r.json()["id"]
    c = _cliente()
    url = f"/svc/{tok}/raster/{item}/{Z}/{X}/{Y}.png"
    assert c.get(url).status_code == 200
    assert sessao_a.delete(f"/api/tokens/{tid}").status_code in (200, 204)
    limite = time.monotonic() + rotas_tiles.AUTH_TTL_S + 3.0
    while time.monotonic() < limite:
        if c.get(url).status_code == 403:
            break
        time.sleep(0.2)
    resposta = c.get(url)
    assert resposta.status_code == 403 and resposta.json()["erro"] == "token_revogado"


# ---------------------------------------------------------------- cláusula: registro com contagem por token
def test_registro_conta_ladrilhos_por_token(sessao_a, raster_demo):
    from app.imagens import leitura

    item = raster_demo["item_id"]
    r = sessao_a.post("/api/tokens", json={"nome": "zt-tiles-conta", "escopos": ["tiles:ler"]})
    tok, tid = r.json()["token"], r.json()["id"]
    try:
        c = _cliente()
        for dx in range(4):
            assert c.get(f"/svc/{tok}/raster/{item}/{Z}/{X + dx}/{Y}.png").status_code in (200, 204)
        leitura.descarregar()
        linhas = sessao_a.get("/api/tiles/leituras").json()["tokens"]
        meu = [li for li in linhas if li["token_id"] == tid]
        assert meu and meu[0]["ladrilhos"] >= 1, linhas
        assert meu[0]["bytes"] > 0 and meu[0]["itens"] == 1
        assert meu[0]["prefixo"] == tok[:12]
    finally:
        sessao_a.delete(f"/api/tokens/{tid}")


def test_registro_nunca_guarda_o_token_em_claro(sessao_a, raster_demo, conexao_plat_app):
    """O registro guarda `token_id`, como `plat.log_acesso`. Nenhuma coluna de texto pode conter o
    token; a tabela nem tem coluna para isso."""
    with conexao_plat_app.cursor() as cur:
        # `plat.` no texto é reescrito para o schema do ambiente (produção, homologação ou trilha);
        # por isso a consulta vai por regclass, e não por `information_schema` com nome de schema fixo.
        cur.execute("SELECT attname FROM pg_attribute WHERE attrelid = 'plat.tile_leitura'::regclass "
                    "AND attnum > 0 AND NOT attisdropped")
        colunas = {r["attname"] for r in cur.fetchall()}
    assert "token_id" in colunas
    assert not (colunas & {"token", "token_valor", "segredo"})


# ---------------------------------------------------------------- mosaico por coleção
def test_mosaico_da_colecao_serve_ladrilho(token_tiles, raster_demo):
    c, tok = _cliente(), token_tiles["token"]
    r = c.get(f"/svc/{tok}/mosaico/{raster_demo['colecao']}/{Z}/{X}/{Y}")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_mosaico_de_colecao_de_outro_inquilino_da_403(token_tiles_b, raster_demo):
    c, tok_b = _cliente(), token_tiles_b["token"]
    r = c.get(f"/svc/{tok_b}/mosaico/{raster_demo['colecao']}/{Z}/{X}/{Y}")
    assert r.status_code == 403 and r.json()["erro"] == "colecao_indisponivel"


def test_item_inexistente_da_403_e_nao_404(token_tiles):
    c, tok = _cliente(), token_tiles["token"]
    r = c.get(f"/svc/{tok}/raster/{uuid.uuid4()}/{Z}/{X}/{Y}.png")
    assert r.status_code == 403


# ---------------------------------------------------------------- cláusula: cliente de mapa (QGIS)
QGIS_UA = "Mozilla/5.0 QGIS/34000/Ubuntu 24.04"


def test_replay_do_que_o_qgis_emite_para_uma_camada_wmts(token_tiles, raster_demo):
    """Não há QGIS instalado nesta máquina (medido em 07/09: `which qgis` vazio; instalar puxa ~1,5 GB
    com o disco a 94 %). O que este teste faz é REPRODUZIR a sequência que o provedor WMTS do QGIS
    emite: GetCapabilities com o User-Agent dele, leitura do `ResourceURL` do documento e busca do
    ladrilho pelo gabarito, trocando {TileMatrix}/{TileCol}/{TileRow}. A prova com um cliente OGC de
    verdade (driver WMTS do GDAL, que abre o serviço e lê pixels) está no handoff do item, com o
    comando; aqui fica a parte que roda sem servidor de pé."""
    import re
    from urllib.parse import urlsplit

    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    caps = c.get(f"/svc/{tok}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml",
                 headers={"User-Agent": QGIS_UA, "Accept": "*/*"})
    assert caps.status_code == 200
    gabaritos = re.findall(r'template="([^"]+)"', caps.text)
    assert gabaritos, caps.text[:400]
    alvo = [g for g in gabaritos if g.endswith(".png")][0]
    caminho = urlsplit(alvo.replace("{TileMatrix}", str(Z)).replace("{TileCol}", str(X))
                       .replace("{TileRow}", str(Y))).path
    ladrilho = c.get(caminho, headers={"User-Agent": QGIS_UA})
    assert ladrilho.status_code == 200 and ladrilho.content[:4] == b"\x89PNG"


def test_replay_do_que_o_qgis_emite_para_uma_camada_xyz(token_tiles, raster_demo):
    """Camada 'XYZ Tiles' do QGIS: ele monta a URL do gabarito do TileJSON (ou digitada pelo usuário)
    e pede o ladrilho direto, sem GetCapabilities."""
    from urllib.parse import urlsplit

    c, tok, item = _cliente(), token_tiles["token"], raster_demo["item_id"]
    tj = c.get(f"/svc/{tok}/raster/{item}/tilejson.json", headers={"User-Agent": QGIS_UA}).json()
    caminho = urlsplit(tj["tiles"][0].replace("{z}", str(Z)).replace("{x}", str(X))
                       .replace("{y}", str(Y))).path
    r = c.get(caminho, headers={"User-Agent": QGIS_UA})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
