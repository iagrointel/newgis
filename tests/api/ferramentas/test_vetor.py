"""Item L2-05-b: as 19 ferramentas vetoriais elementares conferidas contra uma segunda implementação, na MESMA
entrada. Quem faz o papel de segunda implementação:

  * shapely 2.x para tudo o que é geometria plana (interseção, união, diferença, dissolver, casco, simplificar,
    centroide, borda, explodir);
  * pyproj.Geod (elipsoide WGS 84) para o que é geodésico (área, perímetro, comprimento, distância do buffer);
  * SQL escrito no próprio teste para as estatísticas do dissolver.

Tolerância: área com 1e-6 relativa (a mesma do portão do item), contagem de feições exata. A camada de entrada
é sempre lida de volta do banco em WKT e entregue ao shapely — nenhum número esperado é escrito à mão.
"""

import datetime
import json
import os
import time
from pathlib import Path

import pytest
from pyproj import Geod, Transformer
from shapely import wkt as swkt
from shapely.geometry import Point
from shapely.ops import unary_union

from tests.api.ferramentas import apoio
from tests.api.ferramentas import apoio_vetor as av

pytestmark = pytest.mark.usefixtures("camadas")

RAIZ = Path(__file__).resolve().parents[3]
MEDIDAS = RAIZ / "tests" / "medidas" / "L2-05-b-vetor-basico.json"
GEOD = Geod(ellps="WGS84")
REL = 1e-6  # tolerância relativa de área declarada no portão do item

# --- entradas: dois conjuntos de polígonos que se cruzam, linhas e um polígono inválido (laço de gravata)
POLIGONOS_A = [
    {"nome": "A1", "valor": 10, "wkt": "POLYGON((-46.60 -23.50,-46.50 -23.50,-46.50 -23.40,-46.60 -23.40,"
                                       "-46.60 -23.50))"},
    {"nome": "A2", "valor": 20, "wkt": "POLYGON((-46.45 -23.50,-46.35 -23.50,-46.35 -23.40,-46.45 -23.40,"
                                       "-46.45 -23.50))"},
    {"nome": "A3", "valor": 10, "wkt": "POLYGON((-46.30 -23.50,-46.25 -23.50,-46.25 -23.45,-46.30 -23.45,"
                                       "-46.30 -23.50))"},
]
POLIGONOS_B = [
    {"nome": "B1", "valor": 1, "wkt": "POLYGON((-46.55 -23.45,-46.40 -23.45,-46.40 -23.35,-46.55 -23.35,"
                                      "-46.55 -23.45))"},
    {"nome": "B2", "valor": 2, "wkt": "POLYGON((-46.44 -23.49,-46.41 -23.49,-46.41 -23.46,-46.44 -23.46,"
                                      "-46.44 -23.49))"},
]
LINHAS = [
    {"nome": "L1", "valor": 1, "wkt": "LINESTRING(-46.60 -23.50,-46.50 -23.50,-46.50 -23.40)"},
    {"nome": "L2", "valor": 2, "wkt": "LINESTRING(-46.40 -23.40,-46.30 -23.30)"},
]
MULTIPARTES = [
    {"nome": "M1", "valor": 1, "wkt": "MULTIPOLYGON(((-46.20 -23.20,-46.18 -23.20,-46.18 -23.18,-46.20 -23.18,"
                                      "-46.20 -23.20)),((-46.16 -23.20,-46.14 -23.20,-46.14 -23.18,-46.16 -23.18,"
                                      "-46.16 -23.20)))"},
    {"nome": "M2", "valor": 2, "wkt": "POLYGON((-46.12 -23.20,-46.10 -23.20,-46.10 -23.18,-46.12 -23.18,"
                                      "-46.12 -23.20))"},
]
# laço de gravata: ST_IsValid = false; sem ST_MakeValid o GEOS recusa a operação booleana
INVALIDOS = [
    {"nome": "X1", "valor": 1, "wkt": "POLYGON((-46.60 -23.50,-46.50 -23.40,-46.50 -23.50,-46.60 -23.40,"
                                      "-46.60 -23.50))"},
]
PONTOS = [{"nome": "P1", "valor": 1, "wkt": "POINT(-46.55 -23.45)"},
          {"nome": "P2", "valor": 2, "wkt": "POINT(-46.42 -23.44)"}]

_medidas: dict = {}


def anotar(chave: str, valor) -> None:
    _medidas[chave] = valor


def carga() -> dict:
    um_min = os.getloadavg()[0]
    livre = 0.0
    for linha in Path("/proc/meminfo").read_text().splitlines():
        if linha.startswith("MemAvailable:"):
            livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    return {"carga_1min": round(um_min, 2), "ram_livre_gb": livre,
            "medido_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}


@pytest.fixture(scope="module")
def camadas(env, sessao_a, criados):
    """Todas as entradas do item, criadas uma vez e apagadas no fim junto com o que as ferramentas geraram."""
    feito = {}
    for chave, feicoes, tipo in [("a", POLIGONOS_A, "Polygon"), ("b", POLIGONOS_B, "Polygon"),
                                 ("linhas", LINHAS, "LineString"), ("multipartes", MULTIPARTES, "Polygon"),
                                 ("invalidos", INVALIDOS, "Polygon"), ("pontos", PONTOS, "Point")]:
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


def rodar(sessao, criados, nome: str, parametros: dict) -> dict:
    r = sessao.post(f"/api/ferramentas/{nome}/executar", json={"parametros": parametros})
    assert r.status_code == 200, r.text
    corpo = r.json()
    criados["demo"].append(corpo["item_id"])
    return corpo


def saida(env, item_id: str, colunas=()) -> list[dict]:
    schema, tabela = av.tabela_do_item(env, "demo", item_id)
    return av.ler_saida(env, "demo", schema, tabela, colunas)


def geometrias(env, item_id: str):
    return [swkt.loads(li["wkt"]) for li in saida(env, item_id)]


def entrada_shapely(env, camada) -> list:
    return [swkt.loads(li["wkt"]) for li in av.ler_saida(env, "demo", camada["schema"], camada["tabela"])]


def primeira(g):
    """A primeira parte de uma geometria multiparte (as ferramentas devolvem Multi por padrão)."""
    return list(g.geoms)[0] if hasattr(g, "geoms") else g


def perto(obtido: float, esperado: float, rel: float = REL) -> bool:
    if esperado == 0:
        return abs(obtido) <= rel
    return abs(obtido - esperado) / abs(esperado) <= rel


# ---------------------------------------------------------------- catálogo
def test_as_dezenove_ferramentas_estao_no_catalogo_com_esquema(sessao_a):
    lista = sessao_a.get("/api/ferramentas").json()
    nomes = {f["nome"] for f in lista}
    esperadas = {"buffer", "recorte", "intersecao", "uniao", "diferenca", "diferenca_simetrica", "dissolver",
                 "mesclar", "explodir", "centroide", "casco", "simplificar", "suavizar", "reprojetar",
                 "calcular_geometria", "pontos_aleatorios", "linhas_para_pontos", "poligonos_para_linhas",
                 "densificar"}
    assert esperadas <= nomes, esperadas - nomes
    for f in lista:
        if f["nome"] in esperadas:
            assert f["esquema"]["properties"], f["nome"]
            assert any(p["direcao"] == "saida" for p in f["parametros"]), f["nome"]
            assert f["limites"].get("feicoes_max") == 2_000_000, f["nome"]
    anotar("ferramentas_registradas", sorted(esperadas))


# ---------------------------------------------------------------- sobreposição contra shapely
def test_recorte_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "recorte", {"camada": camadas["a"]["id"],
                                             "camada_recorte": camadas["b"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    corte = unary_union(entrada_shapely(env, camadas["b"]))
    esperadas = [g.intersection(corte) for g in entrada_shapely(env, camadas["a"])]
    esperadas = [g for g in esperadas if not g.is_empty and g.area > 0]
    assert len(obtidas) == len(esperadas) == 2
    for o, e in zip(obtidas, esperadas, strict=True):
        assert perto(o.area, e.area), (o.area, e.area)
    anotar("recorte", {"feicoes": len(obtidas), "area_obtida": sum(g.area for g in obtidas),
                       "area_shapely": sum(g.area for g in esperadas)})


def test_intersecao_bate_com_shapely_par_a_par(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "intersecao", {"camada_a": camadas["a"]["id"], "camada_b": camadas["b"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    esperadas = [ga.intersection(gb) for ga in entrada_shapely(env, camadas["a"])
                 for gb in entrada_shapely(env, camadas["b"]) if ga.intersects(gb) and ga.intersection(gb).area > 0]
    assert len(obtidas) == len(esperadas) == 3
    assert perto(sum(g.area for g in obtidas), sum(g.area for g in esperadas))
    campos = saida(env, r["item_id"], ("a_nome", "b_nome"))
    assert {(li["a_nome"], li["b_nome"]) for li in campos} == {("A1", "B1"), ("A2", "B1"), ("A2", "B2")}
    anotar("intersecao", {"feicoes": len(obtidas), "area_obtida": sum(g.area for g in obtidas),
                          "area_shapely": sum(g.area for g in esperadas)})


def test_uniao_cobre_a_mesma_area_que_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "uniao", {"camada_a": camadas["a"]["id"], "camada_b": camadas["b"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    ga, gb = entrada_shapely(env, camadas["a"]), entrada_shapely(env, camadas["b"])
    esperada = unary_union(ga + gb)
    assert perto(unary_union(obtidas).area, esperada.area)
    origens = {li["origem"] for li in saida(env, r["item_id"], ("origem",))}
    assert origens == {"ambas", "a", "b"}
    anotar("uniao", {"feicoes": len(obtidas), "area_obtida": unary_union(obtidas).area,
                     "area_shapely": esperada.area})


def test_diferenca_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "diferenca", {"camada": camadas["a"]["id"],
                                               "camada_apagar": camadas["b"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    apagar = unary_union(entrada_shapely(env, camadas["b"]))
    esperadas = [g.difference(apagar) for g in entrada_shapely(env, camadas["a"])]
    esperadas = [g for g in esperadas if not g.is_empty]
    assert len(obtidas) == len(esperadas) == 3
    assert perto(sum(g.area for g in obtidas), sum(g.area for g in esperadas))
    anotar("diferenca", {"feicoes": len(obtidas), "area_obtida": sum(g.area for g in obtidas),
                         "area_shapely": sum(g.area for g in esperadas)})


def test_diferenca_simetrica_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "diferenca_simetrica", {"camada_a": camadas["a"]["id"],
                                                         "camada_b": camadas["b"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    ua = unary_union(entrada_shapely(env, camadas["a"]))
    ub = unary_union(entrada_shapely(env, camadas["b"]))
    esperada = ua.symmetric_difference(ub)
    assert perto(unary_union(obtidas).area, esperada.area)
    anotar("diferenca_simetrica", {"feicoes": len(obtidas), "area_obtida": unary_union(obtidas).area,
                                   "area_shapely": esperada.area})


def test_regra_da_casa_conserta_invalida_e_relata(env, sessao_a, criados, camadas):
    """Entrada com polígono inválido: a operação booleana NÃO estoura, a saída é 100 % válida e a procedência
    diz quantas geometrias foram consertadas."""
    bruta = av.consultar(env, "demo", f'SELECT count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS n '
                                      f'FROM "{camadas["invalidos"]["schema"]}"."{camadas["invalidos"]["tabela"]}"')
    assert bruta[0]["n"] == 1
    r = rodar(sessao_a, criados, "intersecao", {"camada_a": camadas["invalidos"]["id"],
                                                "camada_b": camadas["a"]["id"]})
    schema, tabela = av.tabela_do_item(env, "demo", r["item_id"])
    validas = av.consultar(env, "demo", f'SELECT count(*) AS total, count(*) FILTER (WHERE ST_IsValid(geom)) AS ok '
                                        f'FROM "{schema}"."{tabela}"')[0]
    assert validas["total"] > 0 and validas["ok"] == validas["total"]
    ficha = sessao_a.get(f"/api/itens/{r['item_id']}").json()
    metodo = ficha["dados"]["procedencia"]["metodo"]
    assert "ST_MakeValid" in metodo and "1 geometria" in metodo, metodo
    anotar("regra_da_casa", {"invalidas_na_entrada": 1, "saidas_validas": validas["ok"],
                             "saidas_totais": validas["total"], "metodo": metodo})


def test_sobreposicao_com_crs_misto(env, sessao_a, criados, camadas):
    """Camada B em SIRGAS 2000 / UTM 23S contra camada A em WGS 84: a ferramenta reprojeta e a área bate."""
    con_wkt = []
    for f in POLIGONOS_B:
        p = av.consultar(env, "demo", "SELECT ST_AsText(ST_Transform(ST_GeomFromText(%s, 4326), 31983)) AS w",
                         (f["wkt"],))[0]["w"]
        con_wkt.append({"nome": f["nome"], "valor": f["valor"], "wkt": p})
    b_utm = av.criar_camada_wkt(env, sessao_a, con_wkt, "Polygon", srid=31983, rotulo="b utm")
    criados["demo"].append(b_utm["id"])
    r = rodar(sessao_a, criados, "intersecao", {"camada_a": camadas["a"]["id"], "camada_b": b_utm["id"]})
    obtidas = geometrias(env, r["item_id"])
    esperadas = [ga.intersection(gb) for ga in entrada_shapely(env, camadas["a"])
                 for gb in entrada_shapely(env, camadas["b"]) if ga.intersects(gb) and ga.intersection(gb).area > 0]
    assert len(obtidas) == len(esperadas)
    # a ida e volta pela projeção move os vértices: a tolerância aqui é do reprojetar, não da sobreposição
    assert perto(sum(g.area for g in obtidas), sum(g.area for g in esperadas), 1e-4)
    anotar("crs_misto", {"srid_b": 31983, "feicoes": len(obtidas),
                         "area_obtida": sum(g.area for g in obtidas),
                         "area_shapely_em_4326": sum(g.area for g in esperadas)})


def test_feicao_sem_sobreposicao_sai_vazia_sem_erro(env, sessao_a, criados, camadas):
    longe = av.criar_camada_wkt(env, sessao_a, [{"nome": "F", "valor": 1, "wkt": "POLYGON((-40 -10,-39 -10,"
                                                 "-39 -9,-40 -9,-40 -10))"}], "Polygon", rotulo="longe")
    criados["demo"].append(longe["id"])
    r = rodar(sessao_a, criados, "recorte", {"camada": camadas["a"]["id"], "camada_recorte": longe["id"]})
    assert r["feicoes"] == 0
    anotar("recorte_sem_sobreposicao", {"feicoes": 0})


# ---------------------------------------------------------------- resumo
def test_dissolver_bate_com_shapely_e_a_soma_bate_com_sql_direto(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "dissolver", {"camada": camadas["a"]["id"], "campos": ["valor"],
                                               "estatisticas": ["soma:valor", "contagem", "maximo:valor"]})
    linhas = saida(env, r["item_id"], ("valor", "feicoes_origem", "soma_valor", "contagem", "maximo_valor"))
    assert len(linhas) == 2
    entradas = av.ler_saida(env, "demo", camadas["a"]["schema"], camadas["a"]["tabela"], ("valor",))
    por_valor: dict = {}
    for li in entradas:
        por_valor.setdefault(li["valor"], []).append(swkt.loads(li["wkt"]))
    for li in linhas:
        esperada = unary_union(por_valor[li["valor"]])
        assert perto(swkt.loads(li["wkt"]).area, esperada.area)
        assert li["feicoes_origem"] == len(por_valor[li["valor"]]) == li["contagem"]
    direto = av.consultar(env, "demo", f'SELECT valor, sum(valor) AS soma, max(valor) AS maior '
                                       f'FROM "{camadas["a"]["schema"]}"."{camadas["a"]["tabela"]}" '
                                       f'GROUP BY valor ORDER BY valor')
    esperado = {li["valor"]: (li["soma"], li["maior"]) for li in direto}
    assert {li["valor"]: (li["soma_valor"], li["maximo_valor"]) for li in linhas} == esperado
    anotar("dissolver", {"grupos": len(linhas), "soma_por_grupo": {str(k): v[0] for k, v in esperado.items()}})


def test_casco_convexo_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "casco", {"camada": camadas["a"]["id"], "tipo": "convexo"})
    obtida = geometrias(env, r["item_id"])[0]
    esperada = unary_union(entrada_shapely(env, camadas["a"])).convex_hull
    assert perto(obtida.area, esperada.area)
    r2 = rodar(sessao_a, criados, "casco", {"camada": camadas["a"]["id"], "tipo": "concavo",
                                            "percentual_convexo": 1.0})
    assert perto(geometrias(env, r2["item_id"])[0].area, esperada.area, 1e-3)
    anotar("casco", {"area_obtida": obtida.area, "area_shapely": esperada.area})


def test_calcular_geometria_bate_com_pyproj_geod(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "calcular_geometria", {"camada": camadas["a"]["id"]})
    linhas = saida(env, r["item_id"], ("nome", "area_m2", "perimetro_m", "x", "y"))
    entradas = {f["nome"]: swkt.loads(f["wkt"]) for f in POLIGONOS_A}
    for li in linhas:
        g = entradas[li["nome"]]
        area, perimetro = GEOD.geometry_area_perimeter(g)
        assert perto(li["area_m2"], abs(area), 1e-6), (li["nome"], li["area_m2"], area)
        assert perto(li["perimetro_m"], perimetro, 1e-6)
        assert g.contains(Point(li["x"], li["y"]))
    anotar("calcular_geometria", {"feicoes": len(linhas),
                                  "area_m2": {li["nome"]: li["area_m2"] for li in linhas}})


# ---------------------------------------------------------------- proximidade: buffer
def buffer_geodesico_de_referencia(lon: float, lat: float, raio_m: float, lados: int = 720):
    """Círculo geodésico de referência: `lados` pontos calculados com pyproj.Geod a partir do centro, cada um a
    `raio_m` do centro. É a definição de buffer geodésico — nada de PostGIS entra nesta conta."""
    pontos = [GEOD.fwd(lon, lat, 360.0 * i / lados, raio_m)[:2] for i in range(lados)]
    return swkt.loads("POLYGON((" + ", ".join(f"{x} {y}" for x, y in pontos + [pontos[0]]) + "))")


def test_buffer_geodesico_de_1km_em_23_sul_bate_com_a_referencia_pyproj(env, sessao_a, criados, camadas):
    """Cláusula do portão: área a ≤ 0,05 % do buffer geodésico de referência a 1 km em latitude −23."""
    ponto = av.criar_camada_wkt(env, sessao_a, [{"nome": "C", "valor": 1, "wkt": "POINT(-46.5 -23.0)"}], "Point",
                               rotulo="centro")
    criados["demo"].append(ponto["id"])
    r = rodar(sessao_a, criados, "buffer", {"camada": ponto["id"],
                                            "distancia": {"distance": 1, "units": "esriKilometers"}})
    obtida = geometrias(env, r["item_id"])[0]
    area_obtida = abs(GEOD.geometry_area_perimeter(obtida)[0])
    referencia = buffer_geodesico_de_referencia(-46.5, -23.0, 1000.0)
    area_ref = abs(GEOD.geometry_area_perimeter(referencia)[0])
    desvio = abs(area_obtida - area_ref) / area_ref
    assert desvio <= 0.0005, (area_obtida, area_ref, desvio)
    anotar("buffer_geodesico_1km_lat_menos23",
           {"area_m2_postgis": area_obtida, "area_m2_referencia_pyproj": area_ref,
            "desvio_relativo": desvio, "limite_do_portao": 0.0005})


def test_buffer_plano_bate_com_shapely_em_camada_projetada(env, sessao_a, criados, camadas):
    wkt_utm = av.consultar(env, "demo", "SELECT ST_AsText(ST_Transform(ST_GeomFromText(%s, 4326), 31983)) AS w",
                           (POLIGONOS_A[0]["wkt"],))[0]["w"]
    utm = av.criar_camada_wkt(env, sessao_a, [{"nome": "A1", "valor": 1, "wkt": wkt_utm}], "Polygon", srid=31983,
                              rotulo="a utm")
    criados["demo"].append(utm["id"])
    r = rodar(sessao_a, criados, "buffer", {"camada": utm["id"], "metodo": "plano",
                                            "distancia": {"distance": 500, "units": "esriMeters"}})
    obtida = geometrias(env, r["item_id"])[0]
    esperada = swkt.loads(wkt_utm).buffer(500.0, quad_segs=48)  # o mesmo nº de segmentos por quarto
    assert perto(obtida.area, esperada.area, 1e-6)
    anotar("buffer_plano", {"area_obtida": obtida.area, "area_shapely": esperada.area})


def test_buffer_plano_recusa_camada_geografica(sessao_a, camadas):
    r = sessao_a.post("/api/ferramentas/buffer/executar",
                      json={"parametros": {"camada": camadas["a"]["id"], "metodo": "plano"}})
    assert r.status_code == 422 and r.json()["erro"] == "buffer_plano_em_camada_geografica", r.text


def test_buffer_por_campo_e_anel(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "buffer", {"camada": camadas["pontos"]["id"], "campo_distancia": "valor"})
    areas = [abs(GEOD.geometry_area_perimeter(g)[0]) for g in geometrias(env, r["item_id"])]
    assert len(areas) == 2 and areas[1] > areas[0] * 3  # raio 2 m contra 1 m: área ~4x
    anel = rodar(sessao_a, criados, "buffer", {
        "camada": camadas["pontos"]["id"], "distancia": {"distance": 1000, "units": "esriMeters"},
        "distancia_interna": {"distance": 400, "units": "esriMeters"}})
    g = geometrias(env, anel["item_id"])[0]
    area_anel = abs(GEOD.geometry_area_perimeter(g)[0])
    esperada = abs(GEOD.geometry_area_perimeter(buffer_geodesico_de_referencia(-46.55, -23.45, 1000.0))[0]) - \
        abs(GEOD.geometry_area_perimeter(buffer_geodesico_de_referencia(-46.55, -23.45, 400.0))[0])
    assert abs(area_anel - esperada) / esperada <= 0.001, (area_anel, esperada)
    assert len(g.geoms[0].interiors) == 1  # o anel tem buraco
    anotar("buffer_anel", {"area_m2": area_anel, "area_m2_referencia": esperada})


def test_buffer_recusa_anel_invertido(sessao_a, camadas):
    r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": {
        "camada": camadas["pontos"]["id"], "distancia": {"distance": 100, "units": "esriMeters"},
        "distancia_interna": {"distance": 200, "units": "esriMeters"}}})
    assert r.status_code == 422 and r.json()["erro"] == "anel_invertido", r.text


# ---------------------------------------------------------------- gestão de dado
def test_mesclar_empilha_e_guarda_a_origem(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "mesclar", {"camadas": [camadas["a"]["id"], camadas["b"]["id"]]})
    linhas = saida(env, r["item_id"], ("nome", "camada_origem"))
    assert len(linhas) == len(POLIGONOS_A) + len(POLIGONOS_B)
    assert {li["nome"] for li in linhas} == {f["nome"] for f in POLIGONOS_A + POLIGONOS_B}
    assert len({li["camada_origem"] for li in linhas}) == 2
    ficha = sessao_a.get(f"/api/itens/{r['item_id']}").json()
    derivados = ficha["dados"]["procedencia"]["ferramenta"]["entradas"]
    assert {d["item_id"] for d in derivados} == {camadas["a"]["id"], camadas["b"]["id"]}
    anotar("mesclar", {"feicoes": len(linhas), "entradas": len(derivados)})


def test_explodir_separa_as_partes(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "explodir", {"camada": camadas["multipartes"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    esperadas = []
    for g in entrada_shapely(env, camadas["multipartes"]):
        esperadas.extend(list(g.geoms) if hasattr(g, "geoms") else [g])
    assert len(obtidas) == len(esperadas) == 3
    assert perto(sum(g.area for g in obtidas), sum(g.area for g in esperadas))
    anotar("explodir", {"entrada": camadas["multipartes"]["feicoes"], "saida": len(obtidas)})


def test_centroide_e_ponto_interior_batem_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "centroide", {"camada": camadas["a"]["id"]})
    obtidos = geometrias(env, r["item_id"])
    esperados = [g.centroid for g in entrada_shapely(env, camadas["a"])]
    assert len(obtidos) == len(esperados)
    for o, e in zip(obtidos, esperados, strict=True):
        assert o.distance(e) < 1e-9
    r2 = rodar(sessao_a, criados, "centroide", {"camada": camadas["a"]["id"], "tipo": "ponto_interior"})
    for o, g in zip(geometrias(env, r2["item_id"]), entrada_shapely(env, camadas["a"]), strict=True):
        assert g.contains(o)
    anotar("centroide", {"feicoes": len(obtidos)})


def test_simplificar_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "simplificar", {"camada": camadas["linhas"]["id"],
                                                 "tolerancia": {"distance": 500, "units": "esriMeters"}})
    obtidas = geometrias(env, r["item_id"])
    tol = 500.0 / 111_320.0
    esperadas = [g.simplify(tol, preserve_topology=True) for g in entrada_shapely(env, camadas["linhas"])]
    assert len(obtidas) == len(esperadas)
    for o, e in zip(obtidas, esperadas, strict=True):
        assert perto(o.length, e.length, 1e-9), (o.length, e.length)
    anotar("simplificar", {"tolerancia_graus": tol,
                           "comprimentos": [g.length for g in obtidas]})


def chaikin(coords, iteracoes: int):
    """Corte de esquina de Chaikin escrito aqui, para o teste não conferir o PostGIS com o próprio PostGIS.
    Cada vértice interior vira dois pontos — a 3/4 do segmento que chega e a 1/4 do que sai; os extremos ficam
    onde estão (é o caso `preservar_extremos = true`, o padrão da ferramenta)."""
    pontos = list(coords)
    for _ in range(iteracoes):
        novos = [pontos[0]]
        for i in range(1, len(pontos) - 1):
            (xa, ya), (xb, yb), (xc, yc) = pontos[i - 1], pontos[i], pontos[i + 1]
            novos.append((xa + 0.75 * (xb - xa), ya + 0.75 * (yb - ya)))
            novos.append((xb + 0.25 * (xc - xb), yb + 0.25 * (yc - yb)))
        novos.append(pontos[-1])
        pontos = novos
    return pontos


def test_suavizar_bate_com_chaikin_escrito_no_teste(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "suavizar", {"camada": camadas["linhas"]["id"], "iteracoes": 2})
    obtidas = geometrias(env, r["item_id"])
    entradas = entrada_shapely(env, camadas["linhas"])
    for o, e in zip(obtidas, entradas, strict=True):
        esperado = chaikin(list(primeira(e).coords), 2)
        obtido = list(primeira(o).coords)
        assert len(obtido) == len(esperado), (len(obtido), len(esperado))
        for (xo, yo), (xe, ye) in zip(obtido, esperado, strict=True):
            assert abs(xo - xe) < 1e-9 and abs(yo - ye) < 1e-9
    anotar("suavizar", {"iteracoes": 2, "vertices": [len(primeira(g).coords) for g in obtidas]})


def test_reprojetar_bate_com_pyproj(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "reprojetar", {"camada": camadas["a"]["id"], "srid_destino": 31983})
    obtidas = geometrias(env, r["item_id"])
    t = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
    for o, e in zip(obtidas, entrada_shapely(env, camadas["a"]), strict=True):
        esperado = [t.transform(x, y) for x, y in primeira(e).exterior.coords]
        obtido = list(primeira(o).exterior.coords)
        for (xo, yo), (xe, ye) in zip(obtido, esperado, strict=True):
            assert abs(xo - xe) < 1e-3 and abs(yo - ye) < 1e-3
    ficha = sessao_a.get(f"/api/itens/{r['item_id']}").json()
    assert ficha["dados"]["srid"] == 31983
    anotar("reprojetar", {"srid_destino": 31983, "tolerancia_m": 1e-3})


def test_densificar_respeita_o_intervalo_geodesico(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "densificar", {"camada": camadas["linhas"]["id"],
                                                "intervalo": {"distance": 500, "units": "esriMeters"}})
    maior = 0.0
    for g in geometrias(env, r["item_id"]):
        for parte in (list(g.geoms) if hasattr(g, "geoms") else [g]):
            coords = list(parte.coords)
            for (x1, y1), (x2, y2) in zip(coords, coords[1:], strict=False):
                maior = max(maior, GEOD.inv(x1, y1, x2, y2)[2])
    assert maior <= 500.0 * 1.0001, maior
    anotar("densificar", {"intervalo_m": 500, "maior_segmento_m": maior})


def test_poligonos_para_linhas_bate_com_shapely(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "poligonos_para_linhas", {"camada": camadas["a"]["id"]})
    obtidas = geometrias(env, r["item_id"])
    esperadas = [g.boundary for g in entrada_shapely(env, camadas["a"])]
    assert len(obtidas) == len(esperadas)
    for o, e in zip(obtidas, esperadas, strict=True):
        assert perto(o.length, e.length)
    anotar("poligonos_para_linhas", {"feicoes": len(obtidas),
                                     "comprimento_total": sum(g.length for g in obtidas)})


def test_pontos_aleatorios_ficam_dentro_e_a_semente_repete(env, sessao_a, criados, camadas):
    parametros = {"camada": camadas["a"]["id"], "quantidade": 25, "semente": 42}
    r = rodar(sessao_a, criados, "pontos_aleatorios", parametros)
    pontos = geometrias(env, r["item_id"])
    assert len(pontos) == 25 * len(POLIGONOS_A)
    envelope = unary_union(entrada_shapely(env, camadas["a"]))
    assert all(envelope.covers(p) for p in pontos)
    r2 = rodar(sessao_a, criados, "pontos_aleatorios", parametros)
    assert [p.wkt for p in geometrias(env, r2["item_id"])] == [p.wkt for p in pontos]
    anotar("pontos_aleatorios", {"pontos": len(pontos), "semente": 42, "repetivel": True})


def test_linhas_para_pontos_vertices_e_intervalo(env, sessao_a, criados, camadas):
    r = rodar(sessao_a, criados, "linhas_para_pontos", {"camada": camadas["linhas"]["id"], "modo": "vertices"})
    obtidos = geometrias(env, r["item_id"])
    esperados = sum(len(primeira(g).coords) for g in entrada_shapely(env, camadas["linhas"]))
    assert len(obtidos) == esperados
    r2 = rodar(sessao_a, criados, "linhas_para_pontos", {"camada": camadas["linhas"]["id"], "modo": "intervalo",
                                                         "intervalo": {"distance": 2, "units": "esriKilometers"}})
    total = 0
    for g in entrada_shapely(env, camadas["linhas"]):
        comprimento = GEOD.geometry_length(primeira(g))
        total += max(1, int(comprimento // 2000.0)) + 1
    assert len(geometrias(env, r2["item_id"])) == total
    anotar("linhas_para_pontos", {"vertices": len(obtidos), "por_intervalo_2km": total})


# ---------------------------------------------------------------- volume: sobreposição de duas malhas
def test_intersecao_em_volume_sem_erro_topologico(env, sessao_a, criados, camadas):
    """Cláusula de volume do portão. A cláusula pede 100 mil polígonos por camada; nesta máquina (disco a 93 %,
    carga acima de 8) a malha foi reduzida a 1.156 por camada para caber no orçamento da trilha — o que se
    afirma aqui é a AUSÊNCIA DE ERRO TOPOLÓGICO e a validade de 100 % da saída, não o tempo em escala real,
    que fica registrado como não medido em `tests/medidas`."""
    lado = 34
    a = av.criar_camada_grade(env, sessao_a, lado, lado, 0.01, 0.0, rotulo="malha a")
    b = av.criar_camada_grade(env, sessao_a, lado, lado, 0.01, 0.005, rotulo="malha b")
    criados["demo"].extend([a["id"], b["id"]])
    antes = carga()
    inicio = time.monotonic()
    r = rodar(sessao_a, criados, "intersecao", {"camada_a": a["id"], "camada_b": b["id"]})
    segundos = time.monotonic() - inicio
    schema, tabela = av.tabela_do_item(env, "demo", r["item_id"])
    v = av.consultar(env, "demo", f'SELECT count(*) AS total, count(*) FILTER (WHERE ST_IsValid(geom)) AS ok '
                                  f'FROM "{schema}"."{tabela}"')[0]
    assert v["total"] > 0 and v["ok"] == v["total"]
    anotar("intersecao_em_volume", {
        "feicoes_por_camada": lado * lado, "pares_de_saida": v["total"], "validas": v["ok"],
        "segundos": round(segundos, 2), "escala_do_portao": 100_000,
        "escala_medida_menor_porque": "disco a 93 % e carga acima de 8 na máquina da trilha (07/09)", **antes})


def test_limite_de_feicoes_por_entrada_esta_declarado(sessao_a):
    f = sessao_a.get("/api/ferramentas/intersecao").json()
    assert f["limites"]["feicoes_max"] == 2_000_000
    anotar("limite_feicoes_por_entrada", 2_000_000)
