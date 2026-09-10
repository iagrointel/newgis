"""Ferramentas raster pela API (item L2-05-e): as treze no catálogo, cada família de saída publicada como
deve, proveniência conferível, e a refutação que o adversário pede — nodata não declarado, CRS geográfico
para declividade, polígono fora da extensão e o disco que cada saída consome.

Os rasters entram pelo caminho da ingestão (objeto + STAC + item); as camadas de zonas são criadas como no
apoio do L2-05-a. Tudo o que a suíte cria é apagado no fim pelo destruidor do tipo.
"""

import json
import tempfile
from pathlib import Path

import pytest
import rasterio

from tests.api.ferramentas import apoio, apoio_raster


def _tenant_id(env, slug: str) -> int:
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.tenant_publico(%s)", (slug,))
            return cur.fetchone()["id"]
    finally:
        con.close()


@pytest.fixture(scope="module")
def arquivos():
    with tempfile.TemporaryDirectory(prefix="zt-raster-") as tmp:
        raiz = Path(tmp)
        yield {
            "dem": apoio_raster.gerar_dem(raiz / "dem.tif"),
            "dem_geo": apoio_raster.gerar_dem(raiz / "dem_geo.tif", geografico=True),
            "classes": apoio_raster.gerar_classes(raiz / "classes.tif"),
            "duas_bandas": apoio_raster.gerar_duas_bandas(raiz / "duas.tif", nodata=0),
            "sem_nodata": apoio_raster.gerar_duas_bandas(raiz / "sem_nodata.tif", nodata=None),
            "raiz": raiz,
        }


@pytest.fixture(scope="module")
def rasters_a(env, arquivos, criados):
    tid = _tenant_id(env, "demo")
    feitos = {nome: apoio_raster.semear(tid, "demo", arquivos[nome], f"zt raster {nome}")
              for nome in ("dem", "dem_geo", "classes", "duas_bandas", "sem_nodata")}
    for r in feitos.values():
        criados["demo"].append(r["id"])
    return feitos


@pytest.fixture(scope="module")
def raster_b(env, arquivos, criados):
    tid = _tenant_id(env, "demo2")
    r = apoio_raster.semear(tid, "demo2", arquivos["classes"], "zt raster do outro inquilino")
    criados["demo2"].append(r["id"])
    return r


@pytest.fixture(scope="module")
def zonas_a(env, sessao_a, criados):
    """Quatro zonas sobre a grade dos rasters: três dentro, uma inteiramente fora."""
    poligonos = [
        ("dentro grande", apoio_raster.quadrado(20, 20, 100, 80)),
        ("dentro pequena", apoio_raster.quadrado(150, 150, 30, 30)),
        ("meia grade", apoio_raster.quadrado(60.4, 40.6, 45.3, 33.2)),
        ("fora", apoio_raster.quadrado(-2000, -2000, 20, 20)),
    ]
    c = apoio_raster.criar_camada_poligonos(env, sessao_a, "demo", poligonos)
    criados["demo"].append(c["id"])
    return c


def executar(sessao, nome: str, parametros: dict, titulo: str | None = None, espera=200):
    r = sessao.post(f"/api/ferramentas/{nome}/executar",
                    json={"parametros": parametros, "titulo": titulo or f"zt {nome}"})
    assert r.status_code == espera, r.text
    return r.json()


def _stac(sessao, colecao: str, item_id: str) -> dict:
    """O STAC é servido por token de serviço (/svc/<token>/stac), não por sessão: o teste cria um token
    com escopo de leitura de imagens, lê e o revoga."""
    r = sessao.post("/api/tokens", json={"nome": "zt-raster-stac", "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        resposta = sessao.get(f"/svc/{tok['token']}/stac/collections/{colecao}/items/{item_id}")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()
    finally:
        sessao.delete(f"/api/tokens/{tok['id']}")


def ficha(sessao, item_id: str) -> dict:
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- catálogo
def test_as_treze_ferramentas_raster_estao_no_catalogo_com_esquema(sessao_a):
    catalogo = {f["nome"]: f for f in sessao_a.get("/api/ferramentas").json()}
    esperadas = {"estatisticas_zonais", "calculadora_raster", "reclassificar_raster", "recortar_raster",
                 "reprojetar_raster", "mosaico_raster", "terreno_raster", "curvas_de_nivel",
                 "vetorizar_raster", "rasterizar_camada", "amostrar_raster", "visibilidade",
                 "distancia_euclidiana"}
    assert esperadas <= set(catalogo), sorted(esperadas - set(catalogo))
    zonal = catalogo["estatisticas_zonais"]
    assert zonal["esquema"]["properties"]["raster"]["x-tipo-gp"] == "GPRasterDataLayer"
    assert zonal["esquema"]["properties"]["raster"]["x-item-familia"] == "raster"
    assert zonal["esquema"]["properties"]["estatisticas"]["items"]["enum"]
    calc = catalogo["calculadora_raster"]
    assert calc["esquema"]["properties"]["rasters"]["x-tipo-gp"] == "GPMultiValue:GPRasterDataLayer"
    for f in catalogo.values():
        assert any(p["direcao"] == "saida" for p in f["parametros"]), f["nome"]


# ---------------------------------------------------------------- saída vetorial
def test_estatisticas_zonais_publicam_camada_com_estatisticas_e_procedencia(sessao_a, rasters_a, zonas_a,
                                                                            criados, env):
    r = executar(sessao_a, "estatisticas_zonais", {
        "zonas": zonas_a["id"], "raster": rasters_a["classes"]["id"],
        "estatisticas": ["contagem", "soma", "media", "minimo", "maximo", "desvio", "mediana",
                         "majoritario", "classes"],
    })
    criados["demo"].append(r["item_id"])
    assert r["sincrono"] is True and r["feicoes"] == 4
    item = ficha(sessao_a, r["item_id"])
    assert item["tipo"] == "camada_vetorial"
    campos = {c["nome"] for c in item["dados"]["campos"]}
    assert {"zs_contagem", "zs_media", "zs_mediana", "zs_majoritario", "zs_classes"} <= campos
    prov = item["dados"]["procedencia"]["ferramenta"]
    assert prov["ferramenta"] == "estatisticas_zonais"
    assert {e["familia"] for e in prov["entradas"]} == {"camada", "raster"}
    assert {e["item_id"] for e in prov["entradas"]} == {zonas_a["id"], rasters_a["classes"]["id"]}
    # a zona de fora tem contagem zero e as de dentro têm classes somando 100 %
    linhas = _linhas(env, item["dados"]["schema"], item["dados"]["tabela"])
    por_nome = {linha["nome"]: linha for linha in linhas}
    assert set(por_nome) == {"dentro grande", "dentro pequena", "meia grade", "fora"}, linhas
    assert por_nome["fora"]["zs_contagem"] == 0
    assert por_nome["fora"]["zs_media"] is None
    for nome in ("dentro grande", "dentro pequena", "meia grade"):
        assert por_nome[nome]["zs_contagem"] > 0
        classes = por_nome[nome]["zs_classes"]
        assert abs(sum((classes if isinstance(classes, dict) else json.loads(classes)).values()) - 100) < 1e-6


def _linhas(env, schema: str, tabela: str, slug: str = "demo") -> list[dict]:
    """Lê a tabela da camada como `plat_app` NO CONTEXTO do inquilino: a tabela nasce com RLS
    (`plat.camada_preparar`), e sem o contexto a consulta volta vazia — não é erro, é a política."""
    from tests import jobs_sessao
    from tests.api.test_rls import contexto, ids_por_slug

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        contexto(con, ids_por_slug(con)[slug], usuario_id=0, login="teste")
        with con.cursor() as cur:
            cur.execute(f'SELECT * FROM "{schema}"."{tabela}" ORDER BY fid')
            return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def test_derivado_de_liga_o_resultado_as_duas_entradas(sessao_a, rasters_a, zonas_a, criados):
    r = executar(sessao_a, "estatisticas_zonais",
                 {"zonas": zonas_a["id"], "raster": rasters_a["classes"]["id"], "estatisticas": ["media"]})
    criados["demo"].append(r["item_id"])
    rel = sessao_a.get(f"/api/itens/{r['item_id']}/criado-a-partir-de")
    assert rel.status_code == 200, rel.text
    origens = {x["id"] for x in rel.json()}
    assert {zonas_a["id"], rasters_a["classes"]["id"]} <= origens


def test_amostrar_curvas_e_vetorizar(sessao_a, rasters_a, criados, env):
    pontos = apoio.criar_camada(env, sessao_a, "demo", [
        ("p1", 1, -46.50, -23.40), ("p2", 2, -46.51, -23.41)])
    criados["demo"].append(pontos["id"])
    # 1. amostragem: os pontos do apoio estão longe da grade UTM dos rasters -> valor nulo declarado
    r = executar(sessao_a, "amostrar_raster", {"pontos": pontos["id"], "raster": rasters_a["dem"]["id"]})
    criados["demo"].append(r["item_id"])
    item = ficha(sessao_a, r["item_id"])
    assert {"valor_b1"} <= {c["nome"] for c in item["dados"]["campos"]}
    # 2. curvas de nível sobre o modelo de elevação
    r = executar(sessao_a, "curvas_de_nivel", {"raster": rasters_a["dem"]["id"], "intervalo": 25.0})
    criados["demo"].append(r["item_id"])
    curvas = ficha(sessao_a, r["item_id"])
    assert curvas["dados"]["geometria"] == "MultiLineString"
    assert curvas["dados"]["estatisticas"]["feicoes"] > 0
    assert "gdal_contour" in curvas["dados"]["procedencia"]["metodo"]
    # 3. vetorização do raster de classes
    r = executar(sessao_a, "vetorizar_raster", {"raster": rasters_a["classes"]["id"]})
    criados["demo"].append(r["item_id"])
    poligonos = ficha(sessao_a, r["item_id"])
    assert poligonos["dados"]["geometria"] == "MultiPolygon"
    assert poligonos["dados"]["estatisticas"]["feicoes"] > 0


# ---------------------------------------------------------------- saída raster
def test_calculadora_publica_raster_com_stac_cog_e_procedencia(sessao_a, rasters_a, criados):
    r = executar(sessao_a, "calculadora_raster",
                 {"rasters": [rasters_a["duas_bandas"]["id"]], "expressao": "(b2-b1)/(b2+b1)",
                  "tipo_saida": "float32", "nodata": -9999.0}, titulo="zt ndvi")
    criados["demo"].append(r["item_id"])
    assert r["sincrono"] is True
    item = ficha(sessao_a, r["item_id"])
    assert item["tipo"] == "raster"
    dados = item["dados"]
    assert dados["perfil"] == "cientifico" and dados["origem"] == "copiado"
    prov = dados["procedencia"]
    assert prov["ferramenta"]["ferramenta"] == "calculadora_raster"
    assert prov["ferramenta"]["parametros"]["expressao"] == "(b2-b1)/(b2+b1)"
    assert prov["cog"]["compressao"] == "ZSTD" and prov["cog"]["bloco"] == 512
    assert prov["cog"]["niveis_piramide"] >= 1, prov["cog"]   # 768 px > bloco 512: a pirâmide existe
    # o item raster aparece no STAC do inquilino, na coleção de análises
    corpo = _stac(sessao_a, dados["colecao"], dados["stac_id"])
    assert corpo["properties"]["plat:ferramenta"]["ferramenta"] == "calculadora_raster"
    assert corpo["assets"]["cientifico"]["roles"] == ["data"]


def test_terreno_reclassificar_e_distancia_encadeados(sessao_a, rasters_a, criados):
    declividade = executar(sessao_a, "terreno_raster",
                           {"raster": rasters_a["dem"]["id"], "produto": "declividade", "unidade": "grau"})
    criados["demo"].append(declividade["item_id"])
    assert "gdaldem slope" in ficha(sessao_a, declividade["item_id"])["dados"]["procedencia"]["metodo"]
    classes = executar(sessao_a, "reclassificar_raster",
                       {"raster": declividade["item_id"], "tabela": "0-5:1;5-15:2;15-*:3",
                        "tipo_saida": "int16"})
    criados["demo"].append(classes["item_id"])
    prov = ficha(sessao_a, classes["item_id"])["dados"]["procedencia"]
    assert prov["resumo"]["fora_das_faixas"] >= 0
    distancia = executar(sessao_a, "distancia_euclidiana",
                         {"raster": classes["item_id"], "valores": [3], "unidade": "mapa"})
    criados["demo"].append(distancia["item_id"])
    assert ficha(sessao_a, distancia["item_id"])["tipo"] == "raster"


def test_recortar_reprojetar_e_mosaico(sessao_a, rasters_a, zonas_a, criados):
    recorte = executar(sessao_a, "recortar_raster",
                       {"raster": rasters_a["classes"]["id"], "mascara": zonas_a["id"]})
    criados["demo"].append(recorte["item_id"])
    reprojetado = executar(sessao_a, "reprojetar_raster",
                           {"raster": rasters_a["dem"]["id"], "epsg": 4326, "reamostragem": "bilinear"})
    criados["demo"].append(reprojetado["item_id"])
    assert ficha(sessao_a, reprojetado["item_id"])["dados"]["srid_nativo"] == 4326
    mosaico = executar(sessao_a, "mosaico_raster",
                       {"rasters": [rasters_a["dem"]["id"], rasters_a["dem"]["id"]],
                        "reamostragem": "vizinho"})
    criados["demo"].append(mosaico["item_id"])
    assert ficha(sessao_a, mosaico["item_id"])["tipo"] == "raster"


def test_rasterizar_camada_e_visibilidade(sessao_a, rasters_a, zonas_a, criados):
    r = executar(sessao_a, "rasterizar_camada",
                 {"camada": zonas_a["id"], "resolucao": 60.0, "tipo_saida": "Float32", "valor": 7.0})
    criados["demo"].append(r["item_id"])
    assert ficha(sessao_a, r["item_id"])["tipo"] == "raster"
    v = executar(sessao_a, "visibilidade",
                 {"raster": rasters_a["dem"]["id"], "ponto": zonas_a["id"], "altura_observador": 10.0})
    criados["demo"].append(v["item_id"])
    prov = ficha(sessao_a, v["item_id"])["dados"]["procedencia"]
    assert "gdal_viewshed" in prov["metodo"]
    assert prov["resumo"]["observador"]


# ---------------------------------------------------------------- refutação do adversário
def test_declividade_em_crs_geografico_e_recusada_com_o_motivo(sessao_a, rasters_a):
    r = sessao_a.post("/api/ferramentas/terreno_raster/executar",
                      json={"parametros": {"raster": rasters_a["dem_geo"]["id"], "produto": "declividade"}})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "crs_geografico"
    assert "escala" in corpo["mensagem"]
    # com a escala declarada, a mesma execução passa
    ok = sessao_a.post("/api/ferramentas/terreno_raster/executar",
                       json={"parametros": {"raster": rasters_a["dem_geo"]["id"], "produto": "declividade",
                                            "escala": 111320.0}})
    assert ok.status_code == 200, ok.text


def test_raster_sem_nodata_declarado_fica_registrado_no_resultado(sessao_a, rasters_a, criados):
    r = executar(sessao_a, "reclassificar_raster",
                 {"raster": rasters_a["sem_nodata"]["id"], "tabela": "0-1000:1;1000-*:2"})
    criados["demo"].append(r["item_id"])
    prov = ficha(sessao_a, r["item_id"])["dados"]["procedencia"]
    assert prov["resumo"]["nodata_declarado"] is False


def test_polinomio_de_recorte_fora_da_extensao_e_erro_nomeado(sessao_a, rasters_a, env, criados):
    fora = apoio_raster.criar_camada_poligonos(env, sessao_a, "demo", [
        ("longe", apoio_raster.quadrado(-5000, -5000, 10, 10))])
    criados["demo"].append(fora["id"])
    r = sessao_a.post("/api/ferramentas/recortar_raster/executar",
                      json={"parametros": {"raster": rasters_a["classes"]["id"], "mascara": fora["id"]}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] in ("sem_intersecao", "recorte_falhou"), r.text


def test_raster_de_outro_inquilino_e_404(sessao_a, raster_b, zonas_a):
    r = sessao_a.post("/api/ferramentas/estatisticas_zonais/executar",
                      json={"parametros": {"zonas": zonas_a["id"], "raster": raster_b["id"]}})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "raster_inexistente"


def test_disco_da_saida_declarado_e_conferido(sessao_a, rasters_a, criados, tmp_path):
    """O adversário mede o disco: o COG de saída tem de trazer compressão e pirâmide declaradas, e o
    tamanho registrado no item tem de ser o do arquivo mesmo."""
    from app import objetos

    r = executar(sessao_a, "reclassificar_raster",
                 {"raster": rasters_a["classes"]["id"], "tabela": "0-2:1;2-*:2", "tipo_saida": "uint8"})
    criados["demo"].append(r["item_id"])
    item = ficha(sessao_a, r["item_id"])
    stac = _stac(sessao_a, item["dados"]["colecao"], item["dados"]["stac_id"])
    chave = stac["assets"]["cientifico"]["href"][len("/api/objetos/"):]
    baixado = tmp_path / "saida.tif"
    objetos.baixar(chave, baixado)
    assert baixado.stat().st_size == stac["assets"]["cientifico"]["file:size"]
    with rasterio.open(baixado) as ds:
        assert ds.profile["compress"].upper() == "ZSTD"
        assert ds.block_shapes[0] == (512, 512)
        assert ds.overviews(1)
    assert item["dados"]["procedencia"]["cog"]["bytes"] == baixado.stat().st_size
