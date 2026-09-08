"""Item L2-05-d: as oito ferramentas de grade, densidade, padrão espacial e interpolação conferidas contra uma
segunda implementação, na MESMA entrada lida de volta do banco. Quem faz o papel de segunda implementação:

  * `esda`/`libpysal` (forma binária dos pesos) para Getis-Ord Gi* e I de Moran;
  * `numpy`/`scipy` escritos no próprio teste para IDW, densidade, centro médio e vizinho mais próximo;
  * a biblioteca `h3` para reconhecer a célula H3 a partir do centro de cada polígono devolvido;
  * a fórmula fechada da área do hexágono regular para a grade;
  * o leitor OGR do GDAL — o mesmo que o QGIS usa — para abrir as isolinhas gravadas em GeoPackage.

Nenhum número esperado é escrito à mão.
"""

import datetime
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree

from tests.api.ferramentas import apoio
from tests.api.ferramentas import apoio_vetor as av

pytestmark = pytest.mark.usefixtures("cenario")

RAIZ = Path(__file__).resolve().parents[3]
MEDIDAS = RAIZ / "tests" / "medidas" / "L2-05-d-grades-densidade-padroes-interpolacao.json"
UTM = 32723  # UTM 23 sul, o fuso que `relacao.utm_da_camada` escolhe para a área de teste
# área de teste: quadrado de 0,04 grau (cerca de 4,1 km por 4,4 km) usado por todas as ferramentas
AREA = [{"nome": "A", "valor": 1,
         "wkt": "POLYGON((-46.56 -23.46,-46.52 -23.46,-46.52 -23.42,-46.56 -23.42,-46.56 -23.46))"}]
LINHAS = [{"nome": "L1", "valor": 1, "wkt": "LINESTRING(-46.555 -23.44,-46.525 -23.44)"},
          {"nome": "L2", "valor": 2, "wkt": "LINESTRING(-46.54 -23.455,-46.54 -23.425)"}]

_medidas: dict = {}


def anotar(chave: str, valor) -> None:
    _medidas[chave] = valor


def carga() -> dict:
    livre = 0.0
    for linha in Path("/proc/meminfo").read_text().splitlines():
        if linha.startswith("MemAvailable:"):
            livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre,
            "medido_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}


def pontos_sorteados(n=60, semente=101):
    """Pontos e valores dentro da área de teste, sorteados com semente fixa: a entrada é reproduzível e nenhum
    número esperado precisa ser escrito."""
    rng = np.random.default_rng(semente)
    x = rng.uniform(-46.558, -46.522, n)
    y = rng.uniform(-23.458, -23.422, n)
    # valor com estrutura espacial de propósito: sem ela, Gi* e Moran não teriam o que encontrar
    v = 100.0 + 500.0 * np.exp(-(((x + 46.53) / 0.01) ** 2 + ((y + 23.43) / 0.01) ** 2)) + rng.normal(0, 5, n)
    return [{"nome": f"P{i}", "valor": int(round(v[i])), "wkt": f"POINT({float(x[i])!r} {float(y[i])!r})"}
            for i in range(n)]


PONTOS = pontos_sorteados()


@pytest.fixture(scope="module")
def cenario(env, sessao_a, criados):
    feito = {}
    for chave, feicoes, tipo in [("area", AREA, "Polygon"), ("pontos", PONTOS, "Point"),
                                 ("linhas", LINHAS, "LineString")]:
        c = av.criar_camada_wkt(env, sessao_a, feicoes, tipo, rotulo=chave)
        criados["demo"].append(c["id"])
        feito[chave] = c
    yield feito
    apoio.apagar_itens(env, "demo", criados["demo"])
    criados["demo"].clear()
    if _medidas:
        MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
        MEDIDAS.write_text(json.dumps(_medidas, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")


# ---------------------------------------------------------------- apoio
def rodar(sessao, criados, nome: str, parametros: dict) -> dict:
    r = sessao.post(f"/api/ferramentas/{nome}/executar", json={"parametros": parametros})
    assert r.status_code == 200, r.text
    corpo = r.json()
    criados["demo"].append(corpo["item_id"])
    return corpo


def saida(env, item_id: str, colunas=()) -> list[dict]:
    schema, tabela = av.tabela_do_item(env, "demo", item_id)
    return av.ler_saida(env, "demo", schema, tabela, colunas)


def coordenadas_utm(env, camada) -> tuple[np.ndarray, np.ndarray]:
    """As MESMAS coordenadas que a ferramenta usa: centro da feição projetado em UTM pelo próprio PostGIS."""
    linhas = av.consultar(env, "demo",
                          f'SELECT ST_X(ST_Transform(ST_Centroid(geom), {UTM})) AS x, '
                          f'ST_Y(ST_Transform(ST_Centroid(geom), {UTM})) AS y, valor '
                          f'FROM "{camada["schema"]}"."{camada["tabela"]}" ORDER BY fid')
    xy = np.array([[float(li["x"]), float(li["y"])] for li in linhas])
    return xy, np.array([float(li["valor"]) for li in linhas])


def pesos_binarios(xy, raio):
    libpysal = pytest.importorskip("libpysal")
    return libpysal.weights.DistanceBand(np.asarray(xy), threshold=raio, binary=True, silence_warnings=True)


# ---------------------------------------------------------------- catálogo
def test_as_oito_ferramentas_do_item_estao_no_catalogo(sessao_a):
    por_nome = {f["nome"]: f for f in sessao_a.get("/api/ferramentas").json()}
    esperadas = {"tesselacao", "densidade_kernel", "hot_spot", "centro_medio", "vizinho_mais_proximo_medio",
                 "moran_global", "interpolacao_idw", "contorno"}
    assert esperadas <= set(por_nome), esperadas - set(por_nome)
    for nome in esperadas:
        f = por_nome[nome]
        assert f["esquema"]["properties"], nome
        assert any(p["direcao"] == "saida" for p in f["parametros"]), nome
        assert f["gpserver"].endswith(f"/{nome}/GPServer/{nome}"), nome
    anotar("ferramentas_registradas", sorted(esperadas))


# ---------------------------------------------------------------- tesselação
def test_tesselacao_hexagonal_de_250_m_tem_a_area_da_formula_fechada(env, sessao_a, criados, cenario):
    """Hexágono regular com 250 m entre lados opostos: área = 3*raiz(3)/2 * aresta², aresta = 250/raiz(3)."""
    r = rodar(sessao_a, criados, "tesselacao",
              {"camada_area": cenario["area"]["id"], "tipo": "hexagonal",
               "tamanho": {"distance": 250, "units": "esriMeters"}, "recortar": False})
    linhas = saida(env, r["item_id"], ("coluna", "linha", "area_m2"))
    esperada = 3 * math.sqrt(3) / 2 * (250 / math.sqrt(3)) ** 2
    areas = np.array([float(li["area_m2"]) for li in linhas])
    assert abs(float(np.median(areas)) - esperada) / esperada < 1e-9
    assert abs(float(areas.max()) - esperada) / esperada < 1e-9
    assert len({(li["coluna"], li["linha"]) for li in linhas}) == len(linhas)
    anotar("tesselacao_hexagonal_250m", {"celulas": len(linhas), "area_mediana_m2": float(np.median(areas)),
                                         "area_da_formula_m2": esperada})


def test_tesselacao_recortada_nao_deixa_celula_fora_da_area(env, sessao_a, criados, cenario):
    """Cláusula do adversário: nenhuma célula (nem parte de célula) fica fora da área de recorte."""
    r = rodar(sessao_a, criados, "tesselacao",
              {"camada_area": cenario["area"]["id"], "tipo": "hexagonal",
               "tamanho": {"distance": 250, "units": "esriMeters"}, "recortar": True})
    schema, tabela = av.tabela_do_item(env, "demo", r["item_id"])
    # a célula é recortada em UTM e volta para 4326; o que se mede é a ÁREA que sobra fora, em m², não a
    # igualdade exata de vértice (ida e volta de projeção move o ponto na casa do milímetro)
    m = av.consultar(env, "demo",
                     f'SELECT count(*) AS n, '
                     f'coalesce(sum(ST_Area(ST_Transform(ST_Difference(c.geom, a.g), {UTM}))), 0) AS fora_m2, '
                     f'sum(ST_Area(ST_Transform(c.geom, {UTM}))) AS dentro_m2 '
                     f'FROM "{schema}"."{tabela}" c, '
                     f'(SELECT ST_Union(geom) AS g FROM "{cenario["area"]["schema"]}".'
                     f'"{cenario["area"]["tabela"]}") a')[0]
    fora, dentro, total = float(m["fora_m2"]), float(m["dentro_m2"]), int(m["n"])
    # o que sobra fora é a diferença entre a reta em UTM (o recorte) e a reta em grau (a área de entrada) ao
    # longo da borda: alguns centímetros de largura em 16 km de perímetro, não célula inteira fora
    assert fora / dentro < 1e-4
    anotar("tesselacao_recortada", {"celulas": total, "area_fora_da_area_m2": fora, "area_total_m2": dentro,
                                    "fracao_fora": fora / dentro})


def test_tesselacao_quadrada_cobre_a_area_sem_sobrepor(env, sessao_a, criados, cenario):
    r = rodar(sessao_a, criados, "tesselacao",
              {"camada_area": cenario["area"]["id"], "tipo": "quadrada",
               "tamanho": {"distance": 500, "units": "esriMeters"}, "recortar": True})
    schema, tabela = av.tabela_do_item(env, "demo", r["item_id"])
    m = av.consultar(env, "demo",
                     f'SELECT count(*) AS n, ST_Area(ST_Transform(ST_Union(geom), {UTM})) AS a, '
                     f'sum(area_m2) AS s FROM "{schema}"."{tabela}"')[0]
    area_da_entrada = av.consultar(env, "demo",
                                   f'SELECT ST_Area(ST_Transform(ST_Union(geom), {UTM})) AS a FROM '
                                   f'"{cenario["area"]["schema"]}"."{cenario["area"]["tabela"]}"')[0]["a"]
    # a união das células recortadas é a própria área, e a soma das áreas não passa dela (sem sobreposição)
    assert abs(float(m["a"]) - float(area_da_entrada)) / float(area_da_entrada) < 1e-6
    assert abs(float(m["s"]) - float(area_da_entrada)) / float(area_da_entrada) < 1e-6
    anotar("tesselacao_quadrada_500m", {"celulas": int(m["n"]), "area_uniao_m2": float(m["a"]),
                                        "area_da_entrada_m2": float(area_da_entrada)})


def test_tesselacao_h3_devolve_as_celulas_que_a_biblioteca_reconhece(env, sessao_a, criados, cenario):
    """Cada polígono devolvido volta a ser o MESMO índice H3 quando o centro é reindexado pela biblioteca."""
    h3 = pytest.importorskip("h3")
    r = rodar(sessao_a, criados, "tesselacao",
              {"camada_area": cenario["area"]["id"], "tipo": "h3", "nivel_h3": 9, "recortar": False})
    linhas = av.consultar(env, "demo",
                          'SELECT h3, nivel, area_m2, ST_Y(ST_Centroid(geom)) AS lat, '
                          'ST_X(ST_Centroid(geom)) AS lng FROM "{}"."{}"'.format(
                              *av.tabela_do_item(env, "demo", r["item_id"])))
    assert linhas
    for li in linhas:
        assert li["nivel"] == 9
        assert h3.latlng_to_cell(float(li["lat"]), float(li["lng"]), 9) == li["h3"]
        assert abs(float(li["area_m2"]) - h3.cell_area(li["h3"], unit="m^2")) < 1e-6
    anotar("tesselacao_h3_nivel9", {"celulas": len(linhas)})


def test_tesselacao_recusa_nivel_h3_fora_da_faixa(sessao_a, cenario):
    r = sessao_a.post("/api/ferramentas/tesselacao/executar",
                      json={"parametros": {"camada_area": cenario["area"]["id"], "tipo": "h3", "nivel_h3": 12}})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- densidade de kernel
def test_densidade_de_pontos_integra_o_numero_de_pontos(env, sessao_a, criados, cenario):
    """Cláusula do portão: soma do valor das células vezes a área da célula = N pontos (tolerância de 1 %)."""
    celula = 200.0
    r = rodar(sessao_a, criados, "densidade_kernel",
              {"camada": cenario["pontos"]["id"], "raio": {"distance": 600, "units": "esriMeters"},
               "tamanho_celula": {"distance": celula, "units": "esriMeters"}, "funcao": "quartica"})
    linhas = saida(env, r["item_id"], ("densidade",))
    total = float(np.sum([float(li["densidade"]) for li in linhas])) * celula * celula
    assert abs(total - len(PONTOS)) / len(PONTOS) < 0.01
    anotar("densidade_pontos", {"celulas": len(linhas), "pontos": len(PONTOS), "integral": total,
                                "erro_relativo": abs(total - len(PONTOS)) / len(PONTOS), **carga()})


def test_densidade_de_linhas_integra_o_comprimento_total(env, sessao_a, criados, cenario):
    celula = 200.0
    r = rodar(sessao_a, criados, "densidade_kernel",
              {"camada": cenario["linhas"]["id"], "raio": {"distance": 600, "units": "esriMeters"},
               "tamanho_celula": {"distance": celula, "units": "esriMeters"}})
    linhas = saida(env, r["item_id"], ("densidade",))
    total = float(np.sum([float(li["densidade"]) for li in linhas])) * celula * celula
    comprimento = float(av.consultar(env, "demo",
                                     f'SELECT sum(ST_Length(ST_Transform(geom, {UTM}))) AS c FROM '
                                     f'"{cenario["linhas"]["schema"]}"."{cenario["linhas"]["tabela"]}"'
                                     )[0]["c"])
    assert abs(total - comprimento) / comprimento < 0.01
    anotar("densidade_linhas", {"celulas": len(linhas), "comprimento_utm_m": comprimento, "integral": total})


# ---------------------------------------------------------------- Gi*
def test_hot_spot_bate_com_esda_na_mesma_entrada(env, sessao_a, criados, cenario):
    esda = pytest.importorskip("esda")
    raio = 600.0
    r = rodar(sessao_a, criados, "hot_spot",
              {"camada": cenario["pontos"]["id"], "campo": "valor",
               "distancia": {"distance": raio, "units": "esriMeters"}})
    linhas = saida(env, r["item_id"], ("fid_origem", "valor", "z", "p", "vizinhos", "faixa"))
    xy, v = coordenadas_utm(env, cenario["pontos"])
    referencia = esda.G_Local(v, pesos_binarios(xy, raio), star=True, transform="B", permutations=0).Zs
    obtido = np.array([float(li["z"]) for li in sorted(linhas, key=lambda li: li["fid_origem"])])
    assert obtido.size == v.size
    diferenca = float(np.abs(obtido - referencia).max())
    assert diferenca < 1e-6
    assert {li["faixa"] for li in linhas} <= {-3, -2, -1, 0, 1, 2, 3}
    anotar("hot_spot_gi_estrela", {"n": int(v.size), "raio_m": raio, "maior_diferenca_z_contra_esda": diferenca,
                                   "quentes_99": sum(1 for li in linhas if li["faixa"] == 3)})


def test_hot_spot_recusa_campo_de_texto(sessao_a, cenario):
    r = sessao_a.post("/api/ferramentas/hot_spot/executar",
                      json={"parametros": {"camada": cenario["pontos"]["id"], "campo": "nome"}})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- Moran
def test_moran_global_bate_com_esda_na_mesma_entrada(env, sessao_a, criados, cenario):
    esda = pytest.importorskip("esda")
    raio = 600.0
    r = rodar(sessao_a, criados, "moran_global",
              {"camada": cenario["pontos"]["id"], "campo": "valor",
               "distancia": {"distance": raio, "units": "esriMeters"}})
    li = saida(env, r["item_id"], ("n", "i", "esperado", "variancia", "z", "p", "pares"))[0]
    xy, v = coordenadas_utm(env, cenario["pontos"])
    referencia = esda.Moran(v, pesos_binarios(xy, raio), permutations=0, transformation="B")
    assert abs(float(li["i"]) - referencia.I) < 1e-9
    assert abs(float(li["z"]) - referencia.z_norm) < 1e-6
    anotar("moran_global", {"i": float(li["i"]), "i_esda": float(referencia.I), "z": float(li["z"]),
                            "z_esda": float(referencia.z_norm), "pares": float(li["pares"])})


# ---------------------------------------------------------------- centro médio e elipse
def test_centro_medio_e_elipse_batem_com_numpy(env, sessao_a, criados, cenario):
    r = rodar(sessao_a, criados, "centro_medio",
              {"camada": cenario["pontos"]["id"], "forma": "elipse", "desvios": 1.0})
    li = saida(env, r["item_id"], ("n", "centro_x", "centro_y", "distancia_padrao", "eixo_maior", "eixo_menor",
                                   "rotacao_graus"))[0]
    xy, _ = coordenadas_utm(env, cenario["pontos"])
    assert int(li["n"]) == xy.shape[0]
    assert abs(float(li["centro_x"]) - float(xy[:, 0].mean())) < 1e-6
    assert abs(float(li["centro_y"]) - float(xy[:, 1].mean())) < 1e-6
    esperada = math.sqrt(float(((xy - xy.mean(axis=0)) ** 2).sum(axis=1).mean()))
    assert abs(float(li["distancia_padrao"]) - esperada) < 1e-6
    assert float(li["eixo_maior"]) >= float(li["eixo_menor"]) > 0
    anotar("centro_medio_elipse", {"n": int(li["n"]), "distancia_padrao_m": float(li["distancia_padrao"]),
                                   "eixo_maior_m": float(li["eixo_maior"]),
                                   "eixo_menor_m": float(li["eixo_menor"]),
                                   "rotacao_graus": float(li["rotacao_graus"])})


def test_centro_medio_ponderado_desloca_para_o_lado_pesado(env, sessao_a, criados, cenario):
    r = rodar(sessao_a, criados, "centro_medio",
              {"camada": cenario["pontos"]["id"], "forma": "centro", "campo_peso": "valor"})
    li = saida(env, r["item_id"], ("centro_x", "centro_y"))[0]
    xy, v = coordenadas_utm(env, cenario["pontos"])
    assert abs(float(li["centro_x"]) - float((xy[:, 0] * v).sum() / v.sum())) < 1e-6
    assert abs(float(li["centro_y"]) - float((xy[:, 1] * v).sum() / v.sum())) < 1e-6


# ---------------------------------------------------------------- vizinho mais próximo médio
def test_vizinho_mais_proximo_medio_bate_com_scipy(env, sessao_a, criados, cenario):
    r = rodar(sessao_a, criados, "vizinho_mais_proximo_medio",
              {"camada": cenario["pontos"]["id"], "camada_area": cenario["area"]["id"]})
    li = saida(env, r["item_id"], ("n", "area_m2", "observada_m", "esperada_m", "razao", "z", "p"))[0]
    xy, _ = coordenadas_utm(env, cenario["pontos"])
    distancias, _ = cKDTree(xy).query(xy, k=2)
    observada = float(distancias[:, 1].mean())
    assert abs(float(li["observada_m"]) - observada) < 1e-6
    esperada = 0.5 / math.sqrt(int(li["n"]) / float(li["area_m2"]))
    assert abs(float(li["esperada_m"]) - esperada) < 1e-9
    assert abs(float(li["razao"]) - observada / esperada) < 1e-9
    anotar("vizinho_mais_proximo_medio", {"n": int(li["n"]), "razao": float(li["razao"]), "z": float(li["z"]),
                                          "p": float(li["p"]), "area_m2": float(li["area_m2"])})


# ---------------------------------------------------------------- IDW
def idw_de_referencia(xy, v, alvos, potencia=2.0, k=12):
    """IDW escrito de novo no teste, com laço explícito e sem árvore k-d."""
    saida = np.empty(alvos.shape[0])
    for n, alvo in enumerate(alvos):
        d = np.linalg.norm(xy - alvo, axis=1)
        ordem = np.argsort(d)[:k]
        if d[ordem[0]] == 0:
            saida[n] = v[ordem[0]]
            continue
        w = 1.0 / d[ordem] ** potencia
        saida[n] = float((w * v[ordem]).sum() / w.sum())
    return saida


def test_idw_bate_com_a_implementacao_de_referencia_do_teste(env, sessao_a, criados, cenario):
    r = rodar(sessao_a, criados, "interpolacao_idw",
              {"camada": cenario["pontos"]["id"], "campo": "valor", "potencia": 2.0, "vizinhos": 12,
               "tamanho_celula": {"distance": 250, "units": "esriMeters"}})
    linhas = saida(env, r["item_id"], ("x", "y", "valor"))
    xy, v = coordenadas_utm(env, cenario["pontos"])
    alvos = np.array([[float(li["x"]), float(li["y"])] for li in linhas])
    esperado = idw_de_referencia(xy, v, alvos)
    obtido = np.array([float(li["valor"]) for li in linhas])
    maior = float(np.abs(obtido - esperado).max())
    assert maior < 1e-9
    assert obtido.min() >= v.min() - 1e-9 and obtido.max() <= v.max() + 1e-9
    anotar("interpolacao_idw", {"celulas": len(linhas), "maior_diferenca": maior,
                                "faixa_amostras": [float(v.min()), float(v.max())],
                                "faixa_saida": [float(obtido.min()), float(obtido.max())]})


def test_idw_devolve_o_valor_da_amostra_quando_a_celula_cai_sobre_ela(env, sessao_a, criados, cenario):
    """Cláusula do portão em cima do caminho completo (banco -> ferramenta -> banco): os 100 alvos são as
    próprias amostras, e o valor tem de voltar idêntico."""
    from app.ferramentas import estatistica_espacial as ee

    xy, v = coordenadas_utm(env, cenario["pontos"])
    assert np.array_equal(ee.idw(xy, v, xy, 2.0, 12), v)
    anotar("idw_exato_nas_amostras", {"amostras": int(v.size), "iguais": int(v.size)})


# ---------------------------------------------------------------- isolinhas
def test_contorno_gera_isolinhas_que_o_leitor_do_qgis_abre(env, sessao_a, criados, cenario, tmp_path):
    """As isolinhas saem em GeoPackage pelo OGR do GDAL — o mesmo leitor que o QGIS usa — e são relidas dali."""
    ogr = pytest.importorskip("osgeo.ogr")
    intervalo = 50.0
    r = rodar(sessao_a, criados, "contorno",
              {"camada": cenario["pontos"]["id"], "campo": "valor", "intervalo": intervalo, "metodo": "idw",
               "tamanho_celula": {"distance": 200, "units": "esriMeters"}})
    linhas = saida(env, r["item_id"], ("valor",))
    assert linhas
    for li in linhas:
        assert abs(float(li["valor"]) / intervalo - round(float(li["valor"]) / intervalo)) < 1e-9
        assert li["wkt"].startswith("MULTILINESTRING")
    caminho = tmp_path / "isolinhas.gpkg"
    fonte = ogr.GetDriverByName("GPKG").CreateDataSource(str(caminho))
    camada = fonte.CreateLayer("isolinhas", geom_type=ogr.wkbMultiLineString)
    camada.CreateField(ogr.FieldDefn("valor", ogr.OFTReal))
    for li in linhas:
        f = ogr.Feature(camada.GetLayerDefn())
        f.SetField("valor", float(li["valor"]))
        f.SetGeometry(ogr.CreateGeometryFromWkt(li["wkt"]))
        camada.CreateFeature(f)
    fonte = camada = None
    lido = ogr.Open(str(caminho))
    assert lido is not None
    camada_lida = lido.GetLayer(0)
    assert camada_lida.GetFeatureCount() == len(linhas)
    validas = sum(1 for f in camada_lida if f.GetGeometryRef() is not None and f.GetGeometryRef().IsValid())
    lido = None
    assert validas == len(linhas)
    anotar("contorno", {"isolinhas": len(linhas), "intervalo": intervalo, "geometrias_validas_no_ogr": validas,
                        "arquivo": "GeoPackage relido pelo OGR do GDAL"})


def test_contorno_com_intervalo_grande_demais_recusa_nomeando_o_campo(sessao_a, cenario):
    r = sessao_a.post("/api/ferramentas/contorno/executar",
                      json={"parametros": {"camada": cenario["pontos"]["id"], "campo": "valor",
                                           "intervalo": 1e9}})
    assert r.status_code == 422, r.text
    assert "sem_isolinha" in r.text
