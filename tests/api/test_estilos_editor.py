"""Item L2-02-c-editor-simbologia-vetor, lado servidor: compilar sem gravar (pré-visualização), estilo salvo
com `camada_id` vira relação estilo_de_camada e o visualizador desenha a camada com ele; classes do estilo
nascem dos cortes do L2-02-b; agrupamento no tile (função `_ag`, contagem por célula conferida contra COUNT(*)
independente e contra ST_ClusterKMeans com tolerância declarada); todo estilo compilado (ícone, padrão, seta,
tracejado, efeitos, escala por classe) valida na Style Spec oficial; TileJSON agrupado; exportar valida."""

import json
import math
import subprocess

import httpx
import pytest

from app.estilos import compilador, validador
from tests import jobs_sessao
from tests.api import estilos_apoio
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-02-c-editor-simbologia-vetor"
MARTIN = "http://127.0.0.1:8436"
TOLERANCIA_KMEANS = 0.6  # fração média de pontos de cada célula que caem no MESMO agrupamento do k-means


@pytest.fixture(scope="module")
def bancada(env):
    return estilos_apoio.criar(env)


@pytest.fixture
def itens_estilo(sessao_a):
    criados = []
    yield criados
    for iid in criados:
        sessao_a.delete(f"/api/itens/{iid}")


def _estilo(sessao, itens, camada_id, pc, titulo="zt estilo editor"):
    dados = {"esquema_versao": 1, "camada_id": camada_id,
             "corpo": {"plat_construtor": pc, "maplibre": compilador.compilar(pc)}}
    r = sessao.post("/api/itens", json={"tipo": "estilo", "titulo": titulo, "dados": dados})
    assert r.status_code == 201, r.text
    itens.append(r.json()["id"])
    return r.json()


def test_compilar_devolve_maplibre_e_legenda_sem_gravar(sessao_a):
    pc = {"tipo": "unico", "geometria": "linha", "versao": 1, "simbolo": {"cor": "#ff0000", "tracejado": [2, 1]}}
    r = sessao_a.post("/api/estilos/compilar", json={"plat_construtor": pc, "id_base": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["maplibre"]["layers"][0]["paint"]["line-dasharray"] == [2.0, 1.0]
    assert r.json()["legenda"] == [{"rotulo": "todas as feições", "cor": "#ff0000"}]
    r = sessao_a.post("/api/estilos/compilar",
                      json={"plat_construtor": {"tipo": "classes", "geometria": "ponto", "versao": 1}})
    assert r.status_code == 422 and r.json()["erro"] == "plat_construtor_invalido", r.text
    assert r.json()["detalhe"]["campo"] == "plat_construtor.campo"


def test_estilo_salvo_com_camada_id_e_o_que_o_visualizador_desenha(sessao_a, bancada, itens_estilo):
    cam = bancada["poligonos"]
    pc = {"tipo": "categoria", "geometria": "poligono", "versao": 1, "campo": "uso", "campos": cam["campos"],
          "categorias": [{"valor": "lavoura", "cor": "#f28e2b"}, {"valor": "pastagem", "cor": "#e15759"}],
          "outros": {"cor": "#9a9a9a", "rotulo": "outros"}, "efeitos": {"sombra": True}, "escala_max": 4000000}
    e = _estilo(sessao_a, itens_estilo, cam["id"], pc)
    rel = sessao_a.get(f"/api/itens/{e['id']}/criado-a-partir-de").json()
    assert any(x["id"] == cam["id"] and x["tipo_relacao"] == "estilo_de_camada" for x in rel), rel
    ficha = sessao_a.get(f"/api/mapa/camadas/{cam['id']}").json()
    assert ficha["estilo_id"] == e["id"] and ficha["plat_construtor"]["tipo"] == "categoria"
    ids = [c["id"] for c in ficha["estilo"]]
    assert ids == [f"plat-{cam['id']}-sombra", f"plat-{cam['id']}", f"plat-{cam['id']}-contorno"]
    assert all(c["source"] == f"plat-{cam['id']}" and c["source-layer"] == "t_" + cam["tabela"][2:]
               for c in ficha["estilo"])
    assert ficha["estilo"][1]["paint"]["fill-color"][-1] == "#9a9a9a"  # feição sem categoria = cor de outros
    assert ficha["estilo"][1]["minzoom"] == compilador.zoom_de_escala(4000000)
    assert [x["cor"] for x in ficha["legenda"]] == ["#f28e2b", "#e15759", "#9a9a9a"]
    # o mais recente vence: um segundo estilo para a mesma camada passa a ser o desenhado
    e2 = _estilo(sessao_a, itens_estilo, cam["id"], {"tipo": "unico", "geometria": "poligono", "versao": 1,
                                                     "simbolo": {"cor": "#123456"}})
    ficha = sessao_a.get(f"/api/mapa/camadas/{cam['id']}").json()
    assert ficha["estilo_id"] == e2["id"] and ficha["legenda"] == [{"rotulo": "todas as feições", "cor": "#123456"}]


def test_classes_do_estilo_sao_os_cortes_do_l2_02_b(sessao_a, bancada, itens_estilo):
    cam = bancada["pontos"]
    r = sessao_a.get(f"/api/camadas/{cam['id']}/classes",
                     params={"campo": "valor", "metodo": "quantil", "n": 5})
    assert r.status_code == 200, r.text
    cortes = r.json()["cortes"]
    assert len(cortes) == 6
    # a mesma função de sugestão do editor (node), com os cortes do servidor
    saida = subprocess.run(["node", "--input-type=module", "-e", f"""
      import {{ createRequire }} from 'node:module'; const require = createRequire(import.meta.url);
      const cb = require('./web/vendor/colorbrewer-1.7.0.js');
      const s = await import('./web/js/mapa/estilo_sugestao.js');
      console.log(JSON.stringify(s.sugerirClasses({json.dumps(cortes)}, s.cores(cb, 'YlGnBu', 5), [2, 12])));
    """], capture_output=True, text=True, check=True, cwd=validador.ROOT if hasattr(validador, "ROOT") else None)
    classes = json.loads(saida.stdout)
    assert [(c["min"], c["max"]) for c in classes] == [(cortes[i], cortes[i + 1]) for i in range(5)]
    pc = {"tipo": "classes", "geometria": "ponto", "versao": 1, "campo": "valor", "campos": cam["campos"],
          "metodo": "quantil", "cortes": cortes, "rampa": "YlGnBu", "classes": classes}
    e = _estilo(sessao_a, itens_estilo, cam["id"], pc)
    lido = sessao_a.get(f"/api/itens/{e['id']}").json()["dados"]["corpo"]
    assert lido["plat_construtor"]["cortes"] == cortes
    raio = lido["maplibre"]["layers"][0]["paint"]["circle-radius"]
    assert raio[0] == "case" and raio[-1] == 12.0 and raio[2] == 2.0  # classes de TAMANHO no tamanho, não só na cor


@pytest.mark.parametrize("pc", [
    {"tipo": "unico", "geometria": "ponto", "versao": 1, "simbolo": {"icone": "energia-poste", "icone_tamanho": 1.2}},
    {"tipo": "unico", "geometria": "linha", "versao": 1,
     "simbolo": {"cor": "#333333", "tracejado": [3, 2], "seta": "setas-seta"}, "efeitos": {"brilho": 3}},
    {"tipo": "unico", "geometria": "poligono", "versao": 1, "simbolo": {"cor": "#59a14f", "padrao": "padrao-hachura"},
     "efeitos": {"sombra": True, "mistura": "multiply"}, "escala_min": 500, "escala_max": 5000000},
    {"tipo": "categoria", "geometria": "ponto", "versao": 1, "campo": "c", "campos": ["c"],
     "categorias": [{"valor": "a", "cor": "#ff0000", "icone": "energia-raio", "escala_max": 100000},
                    {"valor": "b", "cor": "#00ff00"}], "outros": {"cor": "#888888", "visivel": False}},
    {"tipo": "classes", "geometria": "linha", "versao": 1, "campo": "v", "campos": ["v"],
     "classes": [{"min": 0, "max": 1, "cor": "#111111", "tamanho": 1, "escala_min": 1000},
                 {"min": 1, "max": 2, "cor": "#222222", "tamanho": 5}]},
])
def test_estilo_compilado_valida_na_style_spec_oficial(pc):
    validador._chamar_style_spec(compilador.compilar(pc))  # levanta ErroAPI 422 se a Style Spec recusar


def test_exportado_da_ficha_valida_na_style_spec(sessao_a, bancada, itens_estilo):
    cam = bancada["linhas"]
    pc = {"tipo": "classes", "geometria": "linha", "versao": 1, "campo": "extensao_km", "campos": cam["campos"],
          "classes": [{"min": 0, "max": 10, "cor": "#111111", "tamanho": 1},
                      {"min": 10, "max": 40, "cor": "#aa2222", "tamanho": 4}],
          "simbolo": {"seta": "setas-seta"}}
    _estilo(sessao_a, itens_estilo, cam["id"], pc)
    ficha = sessao_a.get(f"/api/mapa/camadas/{cam['id']}").json()
    exportado = {"version": 8, "layers": [{k: v for k, v in c.items() if k not in ("source", "source-layer")}
                                          for c in ficha["estilo"]]}
    validador._chamar_style_spec(exportado)


def _tile_de(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def test_agrupamento_no_tile_bate_com_count_por_celula_e_kmeans(env, bancada, medida):
    cam = bancada["pontos"]
    z = 6
    x, y = _tile_de(estilos_apoio.X0 + 0.2, estilos_apoio.Y0 + 0.15, z)
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid = ids_por_slug(con)["demo"]
        contexto(con, tid, usuario_id=0, login="teste")
        with con.cursor() as cur:
            cur.execute("SELECT point_count, cx, cy FROM plat.camada_agrupar(%s, %s, %s, %s, %s, 40) ORDER BY cx, cy",
                        (cam["schema"], cam["tabela"], z, x, y))
            nossos = cur.fetchall()
            # contagem INDEPENDENTE: mesma grade escrita aqui (célula = 2*40 px do tile de 512 px no z6)
            cel = 40075016.6855785 / (2 ** z) / 512.0 * 80
            cur.execute(
                f'SELECT floor(ST_X(g) / %s) AS cx, floor(ST_Y(g) / %s) AS cy, count(*) AS n FROM '
                f'(SELECT ST_Transform(geom, 3857) AS g FROM "{cam["schema"]}"."{cam["tabela"]}" '
                f'WHERE geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)) p GROUP BY 1, 2 ORDER BY 1, 2',
                (cel, cel, z, x, y))
            independente = cur.fetchall()
            cur.execute(f'SELECT count(*) AS n FROM "{cam["schema"]}"."{cam["tabela"]}" '
                        f'WHERE geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)', (z, x, y))
            total = int(cur.fetchone()["n"])
            k = len(nossos)
            cur.execute(
                f'SELECT floor(ST_X(g) / %s) AS cx, floor(ST_Y(g) / %s) AS cy, '
                f'ST_ClusterKMeans(g, %s) OVER () AS km FROM (SELECT ST_Transform(geom, 3857) AS g FROM '
                f'"{cam["schema"]}"."{cam["tabela"]}" WHERE geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)) p',
                (cel, cel, k, z, x, y))
            pontos = cur.fetchall()
    finally:
        con.close()
    assert total == 1000 and k > 1
    assert sum(int(r["point_count"] or 1) for r in nossos) == total
    assert [(float(r["cx"]), float(r["cy"]), int(r["point_count"] or 1)) for r in nossos] == \
        [(float(r["cx"]), float(r["cy"]), int(r["n"])) for r in independente]
    # k-means independente (mesmo k): para cada célula nossa, a fração dos seus pontos que o k-means pôs no
    # mesmo grupo. Métodos diferentes, comparação com tolerância declarada, nunca igualdade.
    por_celula: dict = {}
    for p in pontos:
        por_celula.setdefault((float(p["cx"]), float(p["cy"])), []).append(p["km"])
    fracoes = []
    for grupos in por_celula.values():
        mais_comum = max(set(grupos), key=grupos.count)
        fracoes.append(grupos.count(mais_comum) / len(grupos))
    concordancia = sum(fracoes) / len(fracoes)
    medida(ITEM)("agrupamento_z6_concordancia_kmeans", round(concordancia, 3), "fração",
                 f"tile z{z}/{x}/{y}: {k} células de 80 px; ST_ClusterKMeans(k={k}); tolerância {TOLERANCIA_KMEANS}")
    assert concordancia >= TOLERANCIA_KMEANS, (concordancia, k)


def test_tilejson_agrupado_serve_tile_pelo_martin(sessao_a, bancada):
    cam = bancada["pontos"]
    try:
        httpx.get(f"{MARTIN}/catalog", timeout=3)
    except httpx.HTTPError as e:
        pytest.skip(f"Martin da trilha fora do ar em {MARTIN}: {e}")
    r = sessao_a.get(f"/api/mapa/camadas/{cam['id']}/tilejson", params={"agrupar": 40})
    assert r.status_code == 200, r.text
    url = r.json()["tiles"][0]
    assert "_ag/" in url and "raio=40" in url and r.json()["vector_layers"][0]["id"].endswith("_ag")
    x, y = _tile_de(estilos_apoio.X0 + 0.2, estilos_apoio.Y0 + 0.15, 6)
    caminho = url.replace("{z}", "6").replace("{x}", str(x)).replace("{y}", str(y)).split("://", 1)[1].split("/", 1)[1]
    t = sessao_a.get("/" + caminho)
    assert t.status_code == 200 and len(t.content) > 20, (t.status_code, t.headers)
    assert t.headers["content-type"] == "application/vnd.mapbox-vector-tile"
