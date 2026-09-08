"""MapServer e GeometryServer compatíveis com Esri (item L2-04-f).

O que se prova aqui, cláusula por cláusula do portão do item:

* o `MapServer` de um mapa do catálogo lista as camadas do documento, com `spatialReference`,
  `initialExtent` e `capabilities` = Map,Query,Data;
* `/layers` e `/{id}` devolvem os MESMOS metadados do FeatureServer (mesma função, comparada campo a
  campo com a resposta do outro serviço);
* `export` de 1024×768 devolve uma imagem daquele tamanho, no formato pedido (png32, jpg, pdf), e a
  cor do pixel dentro do polígono é a cor que o `drawingInfo` declara para aquela classe;
* `identify` sobre três camadas devolve exatamente as mesmas feições que uma consulta espacial direta
  ao PostGIS (comparação por identificador, não por contagem);
* `legend` devolve uma imagem por classe do estilo, e a cor de cada amostra é a da classe;
* `GeometryServer`: `project` de 100 pontos bate com `ST_Transform` até 1e-9, e a envoltória geodésica
  de 1 km tem área a menos de 0,1 % de `ST_Buffer` sobre `geography`;
* refutação declarada do item: export de 8.000×8.000 é 400 com o limite declarado, `identify` com
  tolerância 0 responde sem erro, e `layerDefs` com SQL injetado é 400 (nunca chega ao banco).

Nada aqui é medido contra o QGIS ou o ArcGIS Pro: nenhum dos dois existe nesta máquina, e a cláusula
que os pede fica registrada como NÃO MEDIDA no handoff do item, não como aprovada."""

from __future__ import annotations

import base64
import io
import json
import os
import secrets
import time

import psycopg2
import psycopg2.extras
import pytest
from PIL import Image

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE, novo_cliente

ITEM = "L2-04-f-mapserver-identify-legend-geometryserver"
# quadrado de teste em graus, perto de São Paulo, longe de qualquer dado real da casa
BASE_X, BASE_Y = -46.70, -23.60
CORES = {"a": "#c81e1e", "b": "#1e64c8", "c": "#1ea05a"}


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="utf-8") as f:
        for linha in f:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / 1024 / 1024, 1)
    return -1.0  # pragma: no cover — /proc/meminfo sempre traz MemAvailable no Linux desta máquina


def _sufixo() -> str:
    return secrets.token_hex(4)


def _ulid() -> str:
    alfabeto = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return "0" + "".join(secrets.choice(alfabeto) for _ in range(25))


class CamadaTeste:
    """Tabela física + item de catálogo + polígonos conhecidos. Mesmo desenho do irmão L2-04-b: sem
    worker, porque o que se mede aqui é o SERVIÇO, e uma tabela criada à mão é indistinguível de uma
    carregada pela ingestão para quem lê o descritor."""

    def __init__(self, env, sessao, titulo: str, deslocamento: float):
        self.env, self.sessao = env, sessao
        self.schema = env["PLAT_SCHEMA_TRABALHO"]
        self.tabela = f"zt_l204f_{_sufixo()}"
        self.deslocamento = deslocamento
        self.item_id: str | None = None
        self.estilo_id: str | None = None
        self._criar_tabela()
        self._criar_item(titulo)

    def _con(self):
        con = psycopg2.connect(self.env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        con.autocommit = True
        return con

    def _criar_tabela(self):
        d = self.deslocamento
        with self._con() as con, con.cursor() as cur:
            cur.execute(
                f'CREATE TABLE "{self.schema}"."{self.tabela}" ('
                "  fid bigserial PRIMARY KEY,"
                "  globalid uuid NOT NULL DEFAULT gen_random_uuid(),"
                "  nome text,"
                "  classe text,"
                "  populacao integer,"
                "  criado_em timestamptz NOT NULL DEFAULT now(),"
                "  atualizado_em timestamptz NOT NULL DEFAULT now(),"
                "  geom geometry(Polygon, 4326))"
            )
            cur.execute(f'CREATE INDEX "ix_{self.tabela}_geom" ON "{self.schema}"."{self.tabela}" USING gist (geom)')
            for i, classe in enumerate(("a", "b", "c")):
                x0 = BASE_X + d + i * 0.02
                y0 = BASE_Y + d
                cur.execute(
                    f'INSERT INTO "{self.schema}"."{self.tabela}"(nome, classe, populacao, geom) '
                    "VALUES (%s, %s, %s, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
                    (f"quadra {classe}{i}", classe, 100 * (i + 1), x0, y0, x0 + 0.01, y0 + 0.01),
                )

    def _criar_item(self, titulo: str):
        r = self.sessao.post("/api/itens", json={
            "tipo": "camada_vetorial",
            "titulo": titulo,
            "resumo": "camada do teste do MapServer",
            "tags": ["teste", "esri"],
            "dados": {"schema": self.schema, "tabela": self.tabela, "geometria": "Polygon", "srid": 4326,
                      "campos": [{"nome": "nome", "tipo": "text"}, {"nome": "classe", "tipo": "text"},
                                 {"nome": "populacao", "tipo": "integer"}],
                      "fonte": "hospedada"},
        })
        assert r.status_code == 201, r.text
        self.item_id = r.json()["id"]

    def dar_estilo_por_categoria(self):
        """Forma canônica do estilo no catálogo: o servidor RECOMPILA o bloco `maplibre` a partir do
        `plat_construtor`, e o compilador da casa faz da ÚLTIMA categoria a cor padrão. Por isso as
        quatro categorias aqui: `a`, `b` e `c` saem como classes nomeadas e `z` como padrão."""
        construtor = {
            "versao": 1, "tipo": "categoria", "geometria": "poligono",
            "campo": "classe", "campos": ["classe"],
            "categorias": [
                {"valor": "a", "rotulo": "classe a", "cor": CORES["a"]},
                {"valor": "b", "rotulo": "classe b", "cor": CORES["b"]},
                {"valor": "c", "rotulo": "classe c", "cor": CORES["c"]},
                {"valor": "z", "rotulo": "outros", "cor": "#cccccc"},
            ],
        }
        maplibre = {"version": 8, "layers": [{"id": "camada", "type": "fill", "paint": {
            "fill-color": ["case",
                           ["==", ["get", "classe"], "a"], CORES["a"],
                           ["==", ["get", "classe"], "b"], CORES["b"],
                           ["==", ["get", "classe"], "c"], CORES["c"],
                           "#cccccc"],
            "fill-opacity": 1.0}}]}
        r = self.sessao.post("/api/itens", json={
            "tipo": "estilo", "titulo": f"{PREFIXO_TESTE} estilo {_sufixo()}",
            "dados": {"esquema_versao": 1, "corpo": {"maplibre": maplibre, "plat_construtor": construtor}}})
        assert r.status_code == 201, r.text
        self.estilo_id = r.json()["id"]
        r = self.sessao.put(f"/api/itens/{self.estilo_id}/relacoes", json={
            "relacoes": [{"destino": self.item_id, "tipo": "estilo_de_camada"}]})
        assert r.status_code == 200, r.text

    def adensar(self, quantas: int):
        """Enche a camada com `quantas` quadrículas dentro da mesma extensão, para que a medida de
        tempo do export seja sobre um desenho de verdade e não sobre nove polígonos."""
        lado = int(quantas ** 0.5) + 1
        passo = 0.06 / lado
        with self._con() as con, con.cursor() as cur:
            cur.execute(
                f'INSERT INTO "{self.schema}"."{self.tabela}"(nome, classe, populacao, geom) '
                "SELECT 'grade ' || i || '-' || j, (ARRAY['a','b','c'])[1 + (i + j) %% 3], i * 10, "
                "       ST_MakeEnvelope(%s + i * %s, %s + j * %s, "
                "                       %s + (i + 0.9) * %s, %s + (j + 0.9) * %s, 4326) "
                "FROM generate_series(0, %s) AS i, generate_series(0, %s) AS j LIMIT %s",
                (BASE_X, passo, BASE_Y, passo, BASE_X, passo, BASE_Y, passo,
                 lado - 1, lado - 1, quantas),
            )

    def apagar(self):
        for iid in (self.estilo_id, self.item_id):
            if iid:
                self.sessao.delete(f"/api/itens/{iid}")
        with self._con() as con, con.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{self.schema}"."{self.tabela}"')


class MapaTeste:
    def __init__(self, sessao, camadas: list[CamadaTeste], titulo: str):
        self.sessao = sessao
        corpo = {
            "camadas": [{"id": _ulid(), "ref": c.item_id, "titulo": f"camada {i}", "visivel": True}
                        for i, c in enumerate(camadas)],
            "crs_exibicao": 3857,
            "extensao_inicial": [BASE_X - 0.05, BASE_Y - 0.05, BASE_X + 0.2, BASE_Y + 0.2],
        }
        r = sessao.post("/api/itens", json={
            "tipo": "mapa", "titulo": titulo, "resumo": "mapa do teste do MapServer",
            "dados": {"esquema_versao": 1, "corpo": corpo}})
        assert r.status_code == 201, r.text
        self.item_id = r.json()["id"]

    def apagar(self):
        self.sessao.delete(f"/api/itens/{self.item_id}")


@pytest.fixture
def camadas_a(env, sessao_a):
    feitas = []
    for i in range(3):
        c = CamadaTeste(env, sessao_a, f"{PREFIXO_TESTE} camada f{i} {_sufixo()}", deslocamento=i * 0.001)
        c.dar_estilo_por_categoria()
        feitas.append(c)
    yield feitas
    for c in feitas:
        c.apagar()


@pytest.fixture
def mapa_a(sessao_a, camadas_a):
    m = MapaTeste(sessao_a, camadas_a, f"{PREFIXO_TESTE} mapa {_sufixo()}")
    yield m
    m.apagar()


@pytest.fixture
def token_a(sessao_a):
    r = sessao_a.post("/api/tokens", json={
        "nome": f"{PREFIXO_TESTE}-mapserver-{_sufixo()}", "escopos": ["catalogo:ler", "camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture
def anonimo():
    return novo_cliente()


def _json(resposta):
    assert resposta.status_code == 200, resposta.text
    return json.loads(resposta.text)


def _raiz(token: str, mapa: MapaTeste) -> str:
    return f"/svc/{token}/rest/services/{mapa.item_id}/MapServer"


def _geometria_server(token: str) -> str:
    return f"/svc/{token}/rest/services/Utilities/Geometry/GeometryServer"


def _extensao_dos_dados() -> tuple[float, float, float, float]:
    """Caixa em WGS 84 que cobre os três polígonos das três camadas de teste."""
    return (BASE_X - 0.005, BASE_Y - 0.005, BASE_X + 0.06, BASE_Y + 0.02)


def _bbox_3857(cur) -> str:
    xmin, ymin, xmax, ymax = _extensao_dos_dados()
    cur.execute(
        "SELECT ST_XMin(g) AS a, ST_YMin(g) AS b, ST_XMax(g) AS c, ST_YMax(g) AS d FROM "
        "(SELECT ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 3857) AS g) x",
        (xmin, ymin, xmax, ymax))
    r = cur.fetchone()
    return f"{r['a']},{r['b']},{r['c']},{r['d']}"


# ---------------------------------------------------------------- descritores
def test_mapserver_lista_as_camadas_do_documento(anonimo, token_a, mapa_a):
    d = _json(anonimo.get(_raiz(token_a, mapa_a), params={"f": "json"}))
    assert d["capabilities"] == "Map,Query,Data"
    assert d["spatialReference"]["wkid"] == 3857
    assert [c["id"] for c in d["layers"]] == [0, 1, 2]
    assert all(c["type"] == "Feature Layer" for c in d["layers"])
    assert d["initialExtent"]["xmin"] == pytest.approx(BASE_X - 0.05)
    assert d["maxImageWidth"] == 4096 and d["maxImageHeight"] == 4096


def test_layers_e_camada_trazem_os_metadados_do_featureserver(anonimo, token_a, mapa_a, camadas_a):
    layers = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/layers", params={"f": "json"}))
    assert len(layers["layers"]) == 3
    uma = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/1", params={"f": "json"}))
    assert uma["id"] == 1
    fs = _json(anonimo.get(
        f"/svc/{token_a}/rest/services/{camadas_a[1].item_id}/FeatureServer/0", params={"f": "json"}))
    # os metadados são os mesmos: mesma função, só id/nome vêm do documento de mapa
    for chave in ("fields", "geometryType", "objectIdField", "extent", "indexes", "drawingInfo",
                  "advancedQueryCapabilities", "supportedQueryFormats"):
        assert uma[chave] == fs[chave], chave


def test_camada_inexistente_no_mapserver_e_404(anonimo, token_a, mapa_a):
    assert anonimo.get(f"{_raiz(token_a, mapa_a)}/9", params={"f": "json"}).status_code == 404
    assert anonimo.get(f"{_raiz(token_a, mapa_a)}/abc", params={"f": "json"}).status_code == 404


def test_mapa_de_outro_inquilino_nao_abre_pelo_token_de_a(anonimo, token_a, sessao_b, env, camadas_a):
    camada_b = CamadaTeste(env, sessao_b, f"{PREFIXO_TESTE} camada B {_sufixo()}", 0.0)
    mapa_b = MapaTeste(sessao_b, [camada_b], f"{PREFIXO_TESTE} mapa B {_sufixo()}")
    try:
        r = anonimo.get(f"/svc/{token_a}/rest/services/{mapa_b.item_id}/MapServer", params={"f": "json"})
        assert r.status_code == 404, r.text
    finally:
        mapa_b.apagar()
        camada_b.apagar()


# ---------------------------------------------------------------- export
def _imagem(resposta) -> Image.Image:
    assert resposta.status_code == 200, resposta.text
    return Image.open(io.BytesIO(resposta.content))


def test_export_1024x768_devolve_imagem_do_tamanho_pedido(anonimo, token_a, mapa_a, conexao_plat_app, medida):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    url = f"{_raiz(token_a, mapa_a)}/export"
    params = {"bbox": bbox, "size": "1024,768", "format": "png32", "f": "image", "dpi": 96}
    anonimo.get(url, params=params)  # primeira chamada aquece o pool e o plano
    inicio = time.perf_counter()
    r = anonimo.get(url, params=params)
    decorrido = time.perf_counter() - inicio
    im = _imagem(r)
    assert r.headers["content-type"] == "image/png"
    assert im.size == (1024, 768)
    assert im.mode == "RGBA"
    carga = os.getloadavg()[0]
    livre_gb = _ram_livre_gb()
    medida(ITEM)("export_1024x768_quente_s", round(decorrido, 3), "s",
                 "GET .../MapServer/export?size=1024,768&format=png32&f=image (2a chamada)")
    medida(ITEM)("export_1024x768_carga_1min", round(carga, 2), "carga",
                 "os.getloadavg()[0] no instante da medida (12 nucleos)")
    medida(ITEM)("export_1024x768_ram_livre_gb", livre_gb, "GB", "MemAvailable de /proc/meminfo")
    # Regra da casa para cláusula de desempenho (brief das trilhas, 07/09): número tirado sob disputa
    # não vale como prova. Com carga acima de 8 em 12 núcleos o teto NÃO é cobrado — a medida fica
    # gravada, e o handoff declara a cláusula como não medida em vez de aprovar ou reprovar por causa
    # da casa. Com a máquina calma, o teto de 1,5 s do portão é cobrado de verdade.
    if carga <= 8:
        assert decorrido <= 1.5, f"export quente levou {decorrido:.3f} s (teto 1,5 s), carga {carga:.2f}"


def test_export_desenha_a_cor_que_o_drawing_info_declara(anonimo, token_a, mapa_a, conexao_plat_app):
    """A cláusula "a imagem é a do estilo" medida sem navegador: o pixel no centro de um polígono da
    classe `a` tem a cor que o `drawingInfo` publica para a classe `a`. Se o desenho e a legenda
    divergissem, este teste cairia."""
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/0", params={"f": "json"}))
    infos = d["drawingInfo"]["renderer"]["uniqueValueInfos"]
    cor_a = tuple(next(i for i in infos if i["value"] == "a")["symbol"]["color"])
    im = _imagem(anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "800,400", "format": "png32", "f": "image", "transparent": "true",
        "layers": "show:0"})).convert("RGBA")
    cores = {c[1] for c in im.getcolors(maxcolors=1 << 20)}
    assert cor_a in cores, f"a cor da classe 'a' ({cor_a}) não aparece na imagem"


def test_export_f_json_traz_href_extensao_e_a_mesma_imagem(anonimo, token_a, mapa_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "300,200", "format": "png32", "f": "json"}))
    assert d["width"] == 300 and d["height"] == 200
    assert d["contentType"] == "image/png"
    assert d["extent"]["spatialReference"]["wkid"] == 3857
    assert "f=image" in d["href"]
    im = Image.open(io.BytesIO(base64.b64decode(d["imageData"])))
    assert im.size == (300, 200)


@pytest.mark.parametrize("formato,tipo,pil", [
    ("png32", "image/png", "PNG"), ("png", "image/png", "PNG"), ("png8", "image/png", "PNG"),
    ("jpg", "image/jpeg", "JPEG"),
])
def test_export_nos_formatos_de_imagem_declarados(anonimo, token_a, mapa_a, conexao_plat_app, formato, tipo, pil):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "200,150", "format": formato, "f": "image"})
    assert r.headers["content-type"] == tipo
    im = _imagem(r)
    assert im.format == pil and im.size == (200, 150)


def test_export_em_pdf(anonimo, token_a, mapa_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "200,150", "format": "pdf", "f": "image"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_export_de_8000x8000_e_recusado_com_o_limite_declarado(anonimo, token_a, mapa_a, conexao_plat_app):
    """Refutação declarada do item. O 400 vem ANTES de qualquer alocação de imagem."""
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "8000,8000", "format": "png32", "f": "image"})
    assert r.status_code == 400, r.text
    corpo = r.json()
    assert corpo["erro"] == "imagem_grande_demais"
    assert "4096" in json.dumps(corpo, ensure_ascii=False)


@pytest.mark.parametrize("expressao", [
    "populacao > 1; DROP TABLE plat.item",
    "1=1) OR (SELECT 1 FROM plat.usuario)>0",
    "nome = 'x' UNION SELECT senha_hash FROM plat.usuario",
    "populacao > pg_sleep(5)",
])
def test_layer_defs_com_sql_injetado_e_400(anonimo, token_a, mapa_a, conexao_plat_app, expressao):
    """Refutação declarada. `layerDefs` passa pelo MESMO analisador da operação `query`, com lista
    branca de colunas: expressão fora da gramática é 400 e nunca chega ao banco."""
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "100,100", "format": "png32", "f": "image",
        "layerDefs": json.dumps({"0": expressao})})
    assert r.status_code == 400, r.text


def test_layer_defs_valido_filtra_o_que_e_desenhado(anonimo, token_a, mapa_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    base = {"bbox": bbox, "size": "400,200", "format": "png32", "f": "image",
            "transparent": "true", "layers": "show:0"}
    cheia = _imagem(anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params=base)).convert("RGBA")
    vazia = _imagem(anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        **base, "layerDefs": json.dumps({"0": "populacao > 1000000"})})).convert("RGBA")
    assert cheia.tobytes() != vazia.tobytes()
    assert vazia.getextrema()[3] == (0, 0), "com filtro que não casa nada a imagem tem de ficar vazia"


def test_layer_defs_para_camada_inexistente_e_400(anonimo, token_a, mapa_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "100,100", "f": "image", "layerDefs": json.dumps({"7": "populacao > 1"})})
    assert r.status_code == 400 and r.json()["erro"] == "layerdefs_invalido"


def test_export_com_time_declara_por_que_recusa(anonimo, token_a, mapa_a, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        bbox = _bbox_3857(cur)
    conexao_plat_app.rollback()
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={
        "bbox": bbox, "size": "100,100", "f": "image", "time": "1609459200000,1640995200000"})
    assert r.status_code == 422 and r.json()["erro"] == "time_fora"


@pytest.mark.parametrize("params,codigo", [
    ({"bbox": "0,0,1", "size": "10,10"}, 400),
    ({"bbox": "10,10,1,1", "size": "10,10"}, 400),
    ({"bbox": "0,0,1,1", "size": "0,10"}, 400),
    ({"bbox": "0,0,1,1", "size": "10,10", "dpi": "99999"}, 400),
    ({"bbox": "0,0,1,1", "size": "10,10", "format": "svg"}, 400),
    ({"bbox": "0,0,1,1", "size": "10,10", "layers": "mostrar:0"}, 400),
])
def test_export_recusa_pedido_malformado_sem_500(anonimo, token_a, mapa_a, params, codigo):
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/export", params={**params, "f": "image"})
    assert r.status_code == codigo, r.text


def test_export_de_mapa_denso_fica_dentro_do_teto_de_um_segundo_e_meio(
        env, sessao_a, anonimo, token_a, conexao_plat_app, medida):
    """A mesma medida do teste anterior, mas sobre um desenho de verdade: 5.000 polígonos numa camada,
    1024×768. Sem isto o número de 9 polígonos não diria nada sobre o produto."""
    camada = CamadaTeste(env, sessao_a, f"{PREFIXO_TESTE} camada densa {_sufixo()}", 0.0)
    camada.dar_estilo_por_categoria()
    camada.adensar(5000)
    mapa = MapaTeste(sessao_a, [camada], f"{PREFIXO_TESTE} mapa denso {_sufixo()}")
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{camada.schema}"."{camada.tabela}"')  # noqa: S608
            quantas = cur.fetchone()["n"]
            bbox = _bbox_3857(cur)
        conexao_plat_app.rollback()
        url = f"{_raiz(token_a, mapa)}/export"
        params = {"bbox": bbox, "size": "1024,768", "format": "png32", "f": "image"}
        anonimo.get(url, params=params)
        inicio = time.perf_counter()
        r = anonimo.get(url, params=params)
        decorrido = time.perf_counter() - inicio
        assert _imagem(r).size == (1024, 768)
        carga = os.getloadavg()[0]
        medida(ITEM)("export_denso_feicoes", quantas, "feicoes", "count(*) da camada do teste denso")
        medida(ITEM)("export_denso_1024x768_quente_s", round(decorrido, 3), "s",
                     "GET .../MapServer/export?size=1024,768 sobre a camada densa (2a chamada)")
        medida(ITEM)("export_denso_carga_1min", round(carga, 2), "carga", "os.getloadavg()[0]")
        if carga <= 8:
            assert decorrido <= 1.5, f"export denso levou {decorrido:.3f} s (teto 1,5 s), carga {carga:.2f}"
    finally:
        mapa.apagar()
        camada.apagar()


# ---------------------------------------------------------------- identify
def _fids_da_consulta_direta(cur, camada: CamadaTeste, wkt: str, tolerancia: float) -> set[int]:
    alvo = "ST_GeomFromEWKT(%s)"
    params = [wkt]
    if tolerancia > 0:
        alvo = f"ST_Buffer({alvo}, %s)"
        params.append(tolerancia)
    cur.execute(
        f'SELECT fid FROM "{camada.schema}"."{camada.tabela}" WHERE ST_Intersects(geom, {alvo})',  # noqa: S608
        params)
    return {r["fid"] for r in cur.fetchall()}


def test_identify_em_tres_camadas_bate_com_a_consulta_espacial_direta(
        anonimo, token_a, mapa_a, camadas_a, conexao_plat_app):
    """Cláusula central do item: o serviço não pode devolver nem mais nem menos do que o PostGIS
    devolveria. A comparação é por identificador de feição, camada a camada — não por contagem."""
    xmin, ymin, xmax, ymax = _extensao_dos_dados()
    ponto = {"x": (xmin + xmax) / 2, "y": (ymin + ymax) / 2, "spatialReference": {"wkid": 4326}}
    mapa_extent = f"{xmin},{ymin},{xmax},{ymax}"
    largura = 800
    tolerancia_px = 4
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/identify", params={
        "geometry": json.dumps(ponto), "geometryType": "esriGeometryPoint", "sr": 4326,
        "tolerance": tolerancia_px, "mapExtent": mapa_extent, "imageDisplay": f"{largura},400,96",
        "layers": "all", "f": "json"}))
    tolerancia = tolerancia_px * (xmax - xmin) / largura
    wkt = f"SRID=4326;POINT({ponto['x']} {ponto['y']})"
    with conexao_plat_app.cursor() as cur:
        esperado = {c_i: _fids_da_consulta_direta(cur, c, wkt, tolerancia)
                    for c_i, c in enumerate(camadas_a)}
    conexao_plat_app.rollback()
    obtido: dict[int, set[int]] = {i: set() for i in range(3)}
    for r in d["results"]:
        obtido[r["layerId"]].add(int(r["attributes"]["fid"]))
    assert obtido == esperado
    assert sum(len(v) for v in esperado.values()) > 0, "o caso de teste precisa tocar alguma feição"


def test_identify_com_tolerancia_zero_responde_sem_erro(anonimo, token_a, mapa_a, camadas_a, conexao_plat_app):
    """Refutação declarada. Tolerância 0 é legítima (o que a geometria toca de verdade) e não pode
    virar divisão por zero nem exigir mapExtent."""
    x = BASE_X + 0.005
    y = BASE_Y + 0.005
    ponto = {"x": x, "y": y, "spatialReference": {"wkid": 4326}}
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/identify", params={
        "geometry": json.dumps(ponto), "geometryType": "esriGeometryPoint", "sr": 4326,
        "tolerance": 0, "layers": "all", "f": "json"}))
    wkt = f"SRID=4326;POINT({x} {y})"
    with conexao_plat_app.cursor() as cur:
        esperado = {i: _fids_da_consulta_direta(cur, c, wkt, 0.0) for i, c in enumerate(camadas_a)}
    conexao_plat_app.rollback()
    obtido: dict[int, set[int]] = {i: set() for i in range(3)}
    for r in d["results"]:
        obtido[r["layerId"]].add(int(r["attributes"]["fid"]))
    assert obtido == esperado


def test_identify_com_tolerancia_positiva_sem_tela_e_400(anonimo, token_a, mapa_a):
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/identify", params={
        "geometry": json.dumps({"x": BASE_X, "y": BASE_Y}), "geometryType": "esriGeometryPoint",
        "sr": 4326, "tolerance": 3, "f": "json"})
    assert r.status_code == 400 and r.json()["erro"] == "identify_sem_tela"


def test_identify_top_olha_so_a_primeira_camada(anonimo, token_a, mapa_a):
    xmin, ymin, xmax, ymax = _extensao_dos_dados()
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/identify", params={
        "geometry": json.dumps({"x": (xmin + xmax) / 2, "y": (ymin + ymax) / 2}),
        "geometryType": "esriGeometryPoint", "sr": 4326, "tolerance": 10,
        "mapExtent": f"{xmin},{ymin},{xmax},{ymax}", "imageDisplay": "800,400,96", "f": "json"}))
    assert {r["layerId"] for r in d["results"]} <= {0}


def test_identify_devolve_geometria_esri_quando_pedido(anonimo, token_a, mapa_a):
    xmin, ymin, xmax, ymax = _extensao_dos_dados()
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/identify", params={
        "geometry": json.dumps({"x": (xmin + xmax) / 2, "y": (ymin + ymax) / 2}),
        "geometryType": "esriGeometryPoint", "sr": 4326, "tolerance": 20,
        "mapExtent": f"{xmin},{ymin},{xmax},{ymax}", "imageDisplay": "800,400,96",
        "layers": "all", "returnGeometry": "true", "f": "json"}))
    assert d["results"], "o caso precisa achar alguma feição"
    primeira = d["results"][0]
    assert primeira["geometryType"] == "esriGeometryPolygon"
    assert primeira["geometry"]["rings"] and primeira["geometry"]["spatialReference"]["wkid"] == 4326


# ---------------------------------------------------------------- legend
def test_legend_devolve_uma_imagem_por_classe_do_estilo(anonimo, token_a, mapa_a):
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/legend", params={"f": "json"}))
    assert [c["layerId"] for c in d["layers"]] == [0, 1, 2]
    descritor = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/0", params={"f": "json"}))
    renderer = descritor["drawingInfo"]["renderer"]
    esperadas = len(renderer["uniqueValueInfos"]) + (1 if renderer.get("defaultSymbol") else 0)
    entradas = d["layers"][0]["legend"]
    assert len(entradas) == esperadas, "uma entrada de legenda por classe do estilo"
    cores_do_renderer = [tuple(i["symbol"]["color"]) for i in renderer["uniqueValueInfos"]]
    for entrada, cor in zip(entradas, cores_do_renderer, strict=False):
        im = Image.open(io.BytesIO(base64.b64decode(entrada["imageData"]))).convert("RGBA")
        assert im.size == (20, 20) and entrada["contentType"] == "image/png"
        assert cor in {c[1] for c in im.getcolors(maxcolors=4096)}, entrada["label"]


def test_legend_f_image_devolve_png(anonimo, token_a, mapa_a):
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/legend", params={"f": "image"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (20, 20)


# ---------------------------------------------------------------- find e generateKml
def test_find_acha_pelo_texto_e_declara_o_campo(anonimo, token_a, mapa_a):
    d = _json(anonimo.get(f"{_raiz(token_a, mapa_a)}/find", params={
        "searchText": "quadra b1", "layers": "all", "f": "json"}))
    assert d["results"], "o texto existe em todas as camadas de teste"
    assert all(r["foundFieldName"] == "nome" for r in d["results"])
    assert all("quadra b1" in r["value"] for r in d["results"])


def test_find_com_campo_inexistente_e_400(anonimo, token_a, mapa_a):
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/find", params={
        "searchText": "x", "searchFields": "coluna_que_nao_existe", "layers": "all", "f": "json"})
    assert r.status_code == 400 and r.json()["erro"] == "searchfields_invalido"


def test_generate_kml_devolve_documento_com_uma_pasta_por_camada(anonimo, token_a, mapa_a):
    r = anonimo.get(f"{_raiz(token_a, mapa_a)}/generateKml")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.google-earth.kml+xml")
    texto = r.text
    assert texto.count("<Folder>") == 3
    assert "<Polygon>" in texto and texto.count("<Placemark>") == 9


# ---------------------------------------------------------------- GeometryServer
def test_geometry_server_descritor(anonimo, token_a):
    d = _json(anonimo.get(_geometria_server(token_a), params={"f": "json"}))
    for op in ("Project", "Buffer", "AreasAndLengths", "Lengths", "Simplify", "Union", "Intersect",
               "Difference", "ConvexHull", "Distance"):
        assert op in d["capabilities"]


def test_project_de_100_pontos_bate_com_st_transform(anonimo, token_a, conexao_plat_app, medida):
    """Cláusula do portão: 100 pontos projetados pelo serviço têm de bater com `ST_Transform` até
    1e-9. Não é tautologia: o serviço podia perder precisão na serialização (o `ST_AsGeoJSON` sai com
    12 casas justamente por isso) ou trocar a ordem dos eixos."""
    pontos = [{"x": -46.7 + i * 0.01, "y": -23.6 + i * 0.005} for i in range(100)]
    d = _json(anonimo.post(_geometria_server(token_a) + "/project", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPoint", "geometries": pontos}),
        "inSR": "4326", "outSR": "3857", "f": "json"}))
    assert len(d["geometries"]) == 100
    piores = 0.0
    with conexao_plat_app.cursor() as cur:
        for p, saida in zip(pontos, d["geometries"], strict=True):
            cur.execute("SELECT ST_X(g) AS x, ST_Y(g) AS y FROM (SELECT ST_Transform("
                        "ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857) AS g) t", (p["x"], p["y"]))
            r = cur.fetchone()
            piores = max(piores, abs(r["x"] - saida["x"]), abs(r["y"] - saida["y"]))
    conexao_plat_app.rollback()
    assert piores <= 1e-9, f"maior diferença {piores} m contra ST_Transform"
    medida(ITEM)("project_100_pontos_maior_diferenca_m", piores, "m",
                 "POST .../GeometryServer/project vs ST_Transform no mesmo banco")


def test_buffer_geodesico_de_1km_tem_area_de_st_buffer_geografico(anonimo, token_a, conexao_plat_app, medida):
    ponto = {"x": -46.7, "y": -23.6}
    d = _json(anonimo.post(_geometria_server(token_a) + "/buffer", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPoint", "geometries": [ponto]}),
        "inSR": "4326", "outSR": "4326", "distances": "1000", "unit": "esriSRUnit_Meter",
        "geodesic": "true", "f": "json"}))
    anel = d["geometries"][0]["rings"][0]
    wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in anel) + "))"
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT ST_Area(ST_GeomFromText(%s, 4326)::geography) AS a", (wkt,))
        area_servico = float(cur.fetchone()["a"])
        cur.execute("SELECT ST_Area(ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 1000)) AS a",
                    (ponto["x"], ponto["y"]))
        area_postgis = float(cur.fetchone()["a"])
    conexao_plat_app.rollback()
    erro = abs(area_servico - area_postgis) / area_postgis
    assert erro <= 0.001, f"área do buffer difere {erro:.5%} de ST_Buffer geográfico"
    medida(ITEM)("buffer_1km_erro_relativo_area", round(erro, 8), "fração",
                 "POST .../GeometryServer/buffer (geodesic) vs ST_Buffer(geography, 1000)")


def test_areas_and_lengths_geodesico_bate_com_postgis(anonimo, token_a, conexao_plat_app):
    anel = [[-46.70, -23.60], [-46.69, -23.60], [-46.69, -23.59], [-46.70, -23.59], [-46.70, -23.60]]
    d = _json(anonimo.post(_geometria_server(token_a) + "/areasAndLengths", data={
        "polygons": json.dumps([{"rings": [anel]}]), "sr": "4326",
        "calculationType": "geodesic", "f": "json"}))
    wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in anel) + "))"
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT ST_Area(ST_GeomFromText(%s, 4326)::geography) AS a, "
                    "ST_Perimeter(ST_GeomFromText(%s, 4326)::geography) AS c", (wkt, wkt))
        r = cur.fetchone()
    conexao_plat_app.rollback()
    assert d["areas"][0] == pytest.approx(float(r["a"]), rel=1e-9)
    assert d["lengths"][0] == pytest.approx(float(r["c"]), rel=1e-9)


def test_lengths_e_distance(anonimo, token_a, conexao_plat_app):
    linha = {"paths": [[[-46.70, -23.60], [-46.69, -23.60]]]}
    d = _json(anonimo.post(_geometria_server(token_a) + "/lengths", data={
        "polylines": json.dumps([linha]), "sr": "4326", "calculationType": "geodesic", "f": "json"}))
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT ST_Length(ST_GeomFromText("
                    "'LINESTRING(-46.70 -23.60, -46.69 -23.60)', 4326)::geography) AS c")
        esperado = float(cur.fetchone()["c"])
    conexao_plat_app.rollback()
    assert d["lengths"][0] == pytest.approx(esperado, rel=1e-9)
    dd = _json(anonimo.post(_geometria_server(token_a) + "/distance", data={
        "geometry1": json.dumps({"x": -46.70, "y": -23.60}), "geometryType1": "esriGeometryPoint",
        "geometry2": json.dumps({"x": -46.69, "y": -23.60}), "geometryType2": "esriGeometryPoint",
        "sr": "4326", "geodesic": "true", "f": "json"}))
    assert dd["distance"] == pytest.approx(esperado, rel=1e-9)


def test_union_intersect_difference_convex_hull_e_simplify(anonimo, token_a):
    a = {"rings": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
    b = {"rings": [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}
    corpo = {"geometryType": "esriGeometryPolygon", "geometries": [a, b]}
    u = _json(anonimo.post(_geometria_server(token_a) + "/union", data={
        "geometries": json.dumps(corpo), "sr": "3857", "f": "json"}))
    assert u["geometry"]["rings"]
    i = _json(anonimo.post(_geometria_server(token_a) + "/intersect", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPolygon", "geometries": [a]}),
        "geometry": json.dumps(b), "geometryType": "esriGeometryPolygon", "sr": "3857", "f": "json"}))
    assert i["geometries"][0]["rings"][0][0] is not None
    df = _json(anonimo.post(_geometria_server(token_a) + "/difference", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPolygon", "geometries": [a]}),
        "geometry": json.dumps(b), "geometryType": "esriGeometryPolygon", "sr": "3857", "f": "json"}))
    assert df["geometries"][0]["rings"]
    ch = _json(anonimo.post(_geometria_server(token_a) + "/convexHull", data={
        "geometries": json.dumps(corpo), "sr": "3857", "f": "json"}))
    assert ch["geometry"]["rings"]
    s = _json(anonimo.post(_geometria_server(token_a) + "/simplify", data={
        "geometries": json.dumps(corpo), "sr": "3857", "f": "json"}))
    assert len(s["geometries"]) == 2


@pytest.mark.parametrize("dados,codigo", [
    ({"geometries": "[]", "inSR": "4326", "outSR": "3857"}, 400),
    ({"geometries": "não é json", "inSR": "4326", "outSR": "3857"}, 400),
    ({"geometries": json.dumps([{"x": 1, "y": 2}]), "outSR": "3857"}, 400),
    ({"geometries": json.dumps([{"x": 1, "y": 2}]), "inSR": "4326"}, 400),
])
def test_geometry_server_recusa_pedido_malformado_sem_500(anonimo, token_a, dados, codigo):
    r = anonimo.post(_geometria_server(token_a) + "/project", data={**dados, "f": "json"})
    assert r.status_code == codigo, r.text


def test_buffer_com_distancia_negativa_e_400(anonimo, token_a):
    r = anonimo.post(_geometria_server(token_a) + "/buffer", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPoint", "geometries": [{"x": 0, "y": 0}]}),
        "inSR": "4326", "distances": "-10", "f": "json"})
    assert r.status_code == 400


def test_lote_de_geometrias_acima_do_teto_e_recusado(anonimo, token_a):
    pontos = [{"x": 0.0, "y": 0.0}] * 1001
    r = anonimo.post(_geometria_server(token_a) + "/project", data={
        "geometries": json.dumps({"geometryType": "esriGeometryPoint", "geometries": pontos}),
        "inSR": "4326", "outSR": "3857", "f": "json"})
    assert r.status_code == 413 and r.json()["erro"] == "geometrias_demais"


def test_sem_token_valido_nada_do_mapserver_abre(anonimo, mapa_a):
    falso = "plat_" + secrets.token_urlsafe(32)
    for caminho in ("", "/layers", "/legend", "/export", "/identify", "/find"):
        r = anonimo.get(f"/svc/{falso}/rest/services/{mapa_a.item_id}/MapServer{caminho}",
                        params={"f": "json"})
        assert r.status_code in (401, 403), (caminho, r.status_code)
