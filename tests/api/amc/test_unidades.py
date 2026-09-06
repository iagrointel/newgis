"""Item L3-01-b (conjunto de unidades de análise) pela API, pelo job e por cálculo independente.

Cláusulas do portão provadas aqui:
- grade de 250 m sobre polígono de ~2.000 km² como JOB em ≤ 60 s (medida gravada);
- contagem de células bate com área / área da célula dentro de ± 2 %;
- grade de 100 m sobre área grande: tempo MEDIDO e gravado em tests/medidas/L3-01-b.json (com o disco a 99 % em
  /mnt/pgdata, a medida é feita em 2.500 km² = ~250 mil células e a extrapolação para 1 milhão é DECLARADA na
  própria medida e no handoff — não se finge ter medido o que não se mediu);
- feições com id duplicado recusadas com mensagem em português;
- CRS de trabalho e distorção máxima de área gravados na ficha do conjunto e devolvidos pela API;
- e2e da API: POST cria o conjunto e enfileira o job; depois de o job rodar, a ficha fica completa.

REFUTAÇÃO (a que o adversário repete): a contagem e a área total são conferidas contra shapely/pyproj, fora do
banco, e a área que cruza duas zonas UTM é aceita com CRS e distorção DECLARADOS na ficha, nunca escondidos.

O worker de produção só conhece um tipo de job depois do merge, então aqui a função do job é chamada direto
(`app.amc.unidades.gerar_grade`) com um contexto de teste que implementa db/log/progresso/verificar.
"""

import time
import uuid

import pyproj
import pytest
from shapely.geometry import shape
from shapely.ops import transform

from app import db as banco
from app.amc import unidades
from tests.api.amc import exemplos
from tests.api.test_rls import ids_por_slug

PREFIXO = "zt-amc"


class ContextoDeTeste:
    """O que `gerar_grade` usa do ContextoJob: db(), log(), progresso(), verificar()."""

    def __init__(self, tenant_id: int, usuario_id: int = 0):
        self._ctx = banco.Contexto(tenant_id, usuario_id, "teste")
        self.progressos: list[tuple] = []
        self.linhas_log: list[tuple] = []

    def db(self):
        return banco.db(self._ctx)

    def log(self, nivel: str, mensagem: str) -> None:
        self.linhas_log.append((nivel, mensagem))

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.progressos.append((pct, mensagem))

    def verificar(self) -> None:
        return None


@pytest.fixture
def tenant_a(conexao_plat_app):
    return ids_por_slug(conexao_plat_app)["demo"]


def _area_geodesica_km2(geojson: dict) -> float:
    area, _ = pyproj.Geod(ellps="GRS80").geometry_area_perimeter(shape(geojson))
    return abs(area) / 1e6


def _area_plano_m2(geojson: dict, srid: int) -> float:
    projetar = pyproj.Transformer.from_crs(4326, srid, always_xy=True).transform
    return transform(projetar, shape(geojson)).area


def _retangulo_de(km2_alvo: float, lon0: float = -49.6, lat0: float = -16.9) -> dict:
    """Retângulo em lon/lat cuja área geodésica é ~km2_alvo (ajuste em uma iteração, medido com pyproj.Geod)."""
    lado_graus = (km2_alvo ** 0.5) / 110.0
    area = _area_geodesica_km2(exemplos.area_retangulo(lon0, lat0, lado_graus, lado_graus))
    lado_graus *= (km2_alvo / area) ** 0.5
    return exemplos.area_retangulo(lon0, lat0, lado_graus, lado_graus)


def _gerar(sessao, tenant_id: int, nome: str, tipo: str, lado_m: float, area: dict) -> tuple[dict, float, dict]:
    """POST (job enfileirado) + execução direta da função do job. Devolve (conjunto criado, segundos, ficha)."""
    r = sessao.post("/api/amc/conjuntos", json={"nome": nome, "tipo": tipo, "lado_m": lado_m, "area_estudo": area})
    assert r.status_code == 201, r.text
    criado = r.json()
    assert criado["estado"] == "pendente" and criado["job_id"], "a grade tem de nascer como job"
    ctx = ContextoDeTeste(tenant_id)
    t0 = time.monotonic()
    ficha = unidades.gerar_grade(ctx, criado["id"])
    segundos = time.monotonic() - t0
    assert ctx.progressos and ctx.progressos[-1][0] == 100
    return criado, segundos, ficha


# ---------------------------------------------------------------- grade de 250 m sobre 2.000 km²
@pytest.mark.lento
def test_grade_250m_sobre_2000km2_em_ate_60s_com_contagem_dentro_de_2_por_cento(sessao_a, tenant_a, medida):
    area = _retangulo_de(2000.0)
    km2 = _area_geodesica_km2(area)
    assert 1900 < km2 < 2100, km2
    criado, segundos, ficha = _gerar(sessao_a, tenant_a, f"{PREFIXO} grade 250", "quadrada", 250.0, area)
    try:
        assert segundos <= 60.0, f"a grade levou {segundos:.1f} s (teto do portão: 60 s)"

        # contagem esperada por cálculo independente (shapely/pyproj), não pela conta do próprio motor
        area_plano = _area_plano_m2(area, ficha["srid_trabalho"])
        esperado = area_plano / (250.0 * 250.0)
        desvio_pct = (ficha["n_unidades"] - esperado) / esperado * 100.0
        assert abs(desvio_pct) <= 2.0, (ficha["n_unidades"], esperado, desvio_pct)

        # a soma das áreas geodésicas das células reproduz a área da região de estudo (o recorte não perde nem
        # duplica área): as células de borda entram recortadas
        soma_km2 = ficha["area_total_geodesica_m2"] / 1e6
        assert abs(soma_km2 - km2) / km2 <= 0.005, (soma_km2, km2)

        # a ficha declara o CRS e a distorção; ninguém precisa perguntar
        assert ficha["srid_trabalho"] == 31982 and ficha["crs_nome"].startswith("SIRGAS 2000")
        assert abs(ficha["distorcao_area_max_abs_pct"]) < 1.0

        gravar = medida("L3-01-b")
        gravar("grade_250m_2000km2_segundos", round(segundos, 2), "s",
               "pytest tests/api/amc/test_unidades.py -k 250m")
        gravar("grade_250m_2000km2_celulas", ficha["n_unidades"], "células",
               "SELECT count(*) FROM plat.amc_unidade WHERE conjunto_id = ...")
        gravar("grade_250m_2000km2_desvio_contagem_pct", round(desvio_pct, 3), "%",
               "(n_unidades − area_plano/area_celula) / (area_plano/area_celula) × 100, área por shapely/pyproj")
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{criado['id']}")


@pytest.mark.lento
def test_grade_100m_area_grande_tempo_medido_e_extrapolacao_declarada(sessao_a, tenant_a, medida):
    """MEDIDO: 100 m sobre 2.500 km² (~250 mil células). NÃO medido: 1 milhão de células — o disco de dados está a
    99 % (13 GB livres em /mnt/pgdata) e um conjunto de 1 mi ocuparia ~4× o desta medida. A extrapolação linear
    vai gravada como campo separado, com o nome dizendo que é extrapolação."""
    area = _retangulo_de(2500.0)
    criado, segundos, ficha = _gerar(sessao_a, tenant_a, f"{PREFIXO} grade 100", "quadrada", 100.0, area)
    try:
        area_plano = _area_plano_m2(area, ficha["srid_trabalho"])
        esperado = area_plano / (100.0 * 100.0)
        desvio_pct = (ficha["n_unidades"] - esperado) / esperado * 100.0
        assert abs(desvio_pct) <= 2.0, (ficha["n_unidades"], esperado, desvio_pct)
        assert ficha["n_unidades"] > 200_000

        with banco.db(banco.Contexto(tenant_a, 0, "teste")) as cur:
            cur.execute("SELECT pg_total_relation_size('plat.amc_unidade') AS b")
            bytes_tabela = cur.fetchone()["b"]

        por_milhao = segundos * 1_000_000 / ficha["n_unidades"]
        gravar = medida("L3-01-b")
        gravar("grade_100m_2500km2_segundos", round(segundos, 2), "s",
               "pytest tests/api/amc/test_unidades.py -k 100m")
        gravar("grade_100m_2500km2_celulas", ficha["n_unidades"], "células", "ficha.n_unidades do conjunto")
        gravar("grade_100m_faixas", ficha["faixas"], "faixas de 100 mil células", "ficha.faixas")
        gravar("grade_100m_1milhao_celulas_EXTRAPOLADO", round(por_milhao, 1), "s (extrapolação linear, NÃO medido)",
               "segundos × 1.000.000 / n_unidades — 1 mi de células não foi gerado: /mnt/pgdata a 99 %")
        gravar("amc_unidade_bytes_com_250mil_celulas", bytes_tabela, "bytes (tabela + índices, inclui espaço já "
               "reservado por rodadas anteriores)", "SELECT pg_total_relation_size('plat.amc_unidade')")
        gravar("amc_unidade_bytes_1milhao_EXTRAPOLADO", round(bytes_tabela * 1_000_000 / ficha["n_unidades"]),
               "bytes (extrapolação linear, NÃO medido)", "bytes × 1.000.000 / n_unidades")
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{criado['id']}")


def test_grade_hexagonal_tambem_bate_a_contagem(sessao_a, tenant_a):
    """Hexágono: a área da célula é 3√3/2 × lado² (ST_HexagonGrid usa o lado como parâmetro `size`).

    Aqui a área é pequena de propósito (50 km² com célula de 250 m), e nessa escala a faixa de borda pesa: a
    tolerância honesta não é uma percentagem fixa, é o número de células que a BORDA pode acrescentar. Toda célula
    que toca a área entra (recortada), então a contagem fica entre o esperado e o esperado mais o perímetro
    dividido pelo lado. O ± 2 % do portão é cobrado no caso do portão (250 m sobre 2.000 km²)."""
    area = _retangulo_de(50.0)
    criado, _segundos, ficha = _gerar(sessao_a, tenant_a, f"{PREFIXO} hex", "hexagonal", 250.0, area)
    try:
        projetar = pyproj.Transformer.from_crs(4326, ficha["srid_trabalho"], always_xy=True).transform
        no_plano = transform(projetar, shape(area))
        esperado = no_plano.area / unidades.area_celula_m2("hexagonal", 250.0)
        borda = no_plano.length / 250.0
        assert esperado <= ficha["n_unidades"] <= esperado + borda, (ficha["n_unidades"], esperado, borda)
        assert ficha["funcao"] == "ST_HexagonGrid"
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{criado['id']}")


def test_e2e_da_api_do_conjunto(sessao_a, tenant_a):
    """POST → GET (pendente, com job) → job roda → GET (pronto, ficha completa) → unidades paginadas → DELETE."""
    area = _retangulo_de(20.0)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} e2e", "tipo": "quadrada", "lado_m": 500.0,
                                                  "area_estudo": area})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        antes = sessao_a.get(f"/api/amc/conjuntos/{cid}").json()
        assert antes["estado"] == "pendente" and antes["n_unidades"] is None
        assert antes["ficha"]["contagem_esperada"] > 0 and antes["ficha"]["srid_trabalho"] == 31982
        unidades.gerar_grade(ContextoDeTeste(tenant_a), cid)

        depois = sessao_a.get(f"/api/amc/conjuntos/{cid}").json()
        assert depois["estado"] == "pronto" and depois["n_unidades"] > 50
        assert depois["ficha"]["tempo_geracao_s"] > 0 and depois["ficha"]["recorte"]
        pagina = sessao_a.get(f"/api/amc/conjuntos/{cid}/unidades?limite=10").json()
        assert pagina["type"] == "FeatureCollection" and len(pagina["features"]) == 10
        assert pagina["total"] == depois["n_unidades"] and pagina["crs_saida"] == 4326
        primeira = pagina["features"][0]
        assert primeira["geometry"]["type"] in ("Polygon", "MultiPolygon") and primeira["properties"]["area_m2"] > 0
        assert "_" in primeira["id"], "o id da célula da grade é '<i>_<j>'"
        sem_geometria = sessao_a.get(f"/api/amc/conjuntos/{cid}/unidades?limite=3&geometria=false").json()
        assert all(f["geometry"] is None for f in sem_geometria["features"])
    finally:
        assert sessao_a.delete(f"/api/amc/conjuntos/{cid}").status_code == 204
    assert sessao_a.get(f"/api/amc/conjuntos/{cid}").status_code == 404


# ---------------------------------------------------------------- feições do usuário
def _colecao(ids: list[str]) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": i, "properties": {"codigo": i},
         "geometry": exemplos.area_retangulo(-49.30 + 0.02 * k, -16.70, 0.01, 0.01)}
        for k, i in enumerate(ids)]}


def test_feicoes_preservam_o_id_do_usuario_e_a_area_geodesica(sessao_a):
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} feicoes", "tipo": "feicoes",
                                                  "feicoes": _colecao(["gleba-A", "gleba-B", "gleba-C"])})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    try:
        assert conjunto["estado"] == "pronto" and conjunto["n_unidades"] == 3
        pagina = sessao_a.get(f"/api/amc/conjuntos/{conjunto['id']}/unidades").json()
        assert [f["id"] for f in pagina["features"]] == ["gleba-A", "gleba-B", "gleba-C"]
        for f in pagina["features"]:
            assert 1_000_000 < f["properties"]["area_m2"] < 1_500_000  # ~1,1 km × ~1,1 km
        assert conjunto["ficha"]["srid_trabalho"] == 31982
        assert conjunto["ficha"]["distorcao_area_max_abs_pct"] is not None
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


def test_feicao_com_id_duplicado_e_recusada_em_portugues(sessao_a):
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} dup", "tipo": "feicoes",
                                                  "feicoes": _colecao(["a", "b", "a"])})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "feicoes_id_duplicado"
    assert "repetido" in corpo["mensagem"] and "único" in corpo["mensagem"]
    assert corpo["detalhe"]["duplicados"]["a"] == [0, 2]
    # e nada foi gravado: a recusa é do conjunto inteiro, não de uma feição
    nomes = [c["nome"] for c in sessao_a.get("/api/amc/conjuntos?limite=200").json()["conjuntos"]]
    assert f"{PREFIXO} dup" not in nomes


def test_feicao_sem_id_e_recusada(sessao_a):
    colecao = _colecao(["a", "b"])
    del colecao["features"][1]["id"]
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} sem id", "tipo": "feicoes", "feicoes": colecao})
    assert r.status_code == 422 and r.json()["erro"] == "feicoes_sem_id"
    assert "id estável" in r.json()["mensagem"]


def test_id_da_feicao_pode_vir_de_uma_propriedade(sessao_a):
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} campo", "tipo": "feicoes",
                                                  "campo_id": "codigo", "feicoes": _colecao(["x1", "x2"])})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    try:
        pagina = sessao_a.get(f"/api/amc/conjuntos/{conjunto['id']}/unidades").json()
        assert [f["id"] for f in pagina["features"]] == ["x1", "x2"]
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


# ---------------------------------------------------------------- CRS declarado, nunca escondido
def test_area_que_cruza_duas_zonas_utm_e_aceita_com_crs_e_distorcao_declarados(sessao_a):
    """Refutação do adversário: 4° de longitude a cavalo do meridiano −48° (zonas 22S e 23S). O conjunto usa um CRS
    só — o da zona do centróide — e a ficha diz isso, com a distorção medida e o aviso escrito."""
    area = exemplos.area_retangulo(-49.5, -16.0, 3.0, 0.2)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} duas zonas", "tipo": "quadrada",
                                                  "lado_m": 5000.0, "area_estudo": area})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    try:
        ficha = conjunto["ficha"]
        assert ficha["cruza_zonas_utm"] is True and ficha["zonas_utm_cobertas"] == [22, 23]
        assert ficha["srid_trabalho"] in (31982, 31983) and conjunto["srid_trabalho"] == ficha["srid_trabalho"]
        assert any("zonas UTM" in a for a in ficha["avisos"])
        assert ficha["distorcao_area_max_abs_pct"] > 0.1, "longe do meridiano central a distorção tem de aparecer"
        assert ficha["metodo"].startswith("pyproj")
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")


def test_grade_grande_demais_e_recusada_antes_de_gerar(sessao_a):
    """O teto de unidades por conjunto é declarado (app/limites.py) e a recusa diz o que fazer."""
    area = _retangulo_de(200_000.0)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} enorme", "tipo": "quadrada", "lado_m": 100.0,
                                                  "area_estudo": area})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "grade_grande_demais"
    assert "aumente o lado ou reduza a área" in r.json()["mensagem"]


def test_area_fora_da_cobertura_do_sirgas_e_recusada(sessao_a):
    area = exemplos.area_retangulo(-100.0, -10.0, 0.05, 0.05)  # zona UTM 14S: fora do SIRGAS 2000 brasileiro
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} fora", "tipo": "quadrada", "lado_m": 250.0,
                                                  "area_estudo": area})
    assert r.status_code == 422 and r.json()["erro"] == "crs_fora_da_cobertura"


def test_conjunto_usado_por_execucao_nao_se_apaga(sessao_a, conexao_plat_app):
    from tests.api.amc.test_modelo import _modelo_com_itens

    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} preso", "tipo": "feicoes",
                                                  "feicoes": _colecao(["p1"])})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    r = sessao_a.post("/api/amc/modelos", json={"definicao": _modelo_com_itens(sessao_a)})
    modelo = r.json()
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"]})
    assert r.status_code == 201, r.text
    execucao = r.json()
    try:
        assert sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}").status_code == 409
    finally:
        sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
        sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


# ================================================================ conserto do laudo L3-01-ADVERSARIO (06/09/2026)
def test_teto_de_unidades_vale_para_a_contagem_real_e_o_job_falha(sessao_a, conexao_plat_app, monkeypatch):
    """Achado 4: o teto era conferido só sobre a ESTIMATIVA área/área-da-célula. A célula de borda entra recortada,
    então o conjunto terminava acima do teto declarado (o adversário mediu 1.000.175 com o teto em 1.000.000).
    Aqui o teto é baixado por monkeypatch para provar a mecânica sem gerar um milhão de células: a estimativa passa
    na guarda de entrada, a contagem real não, e o conjunto tem de terminar VAZIO e marcado como falhou — e o job
    tem de falhar junto, para o operador não ver 'concluído' sobre um conjunto recusado."""
    from app import limites
    from app.amc import tarefas as amc_tarefas
    from app.jobs.registro import FalhaDefinitiva

    tenant = ids_por_slug(conexao_plat_app)["demo"]
    externo = [[-49.50, -16.90], [-49.40, -16.90], [-49.40, -16.80], [-49.50, -16.80], [-49.50, -16.90]]
    buraco = [[-49.47, -16.87], [-49.43, -16.87], [-49.43, -16.83], [-49.47, -16.83], [-49.47, -16.87]]
    monkeypatch.setattr(limites, "AMC_UNIDADES_MAX", 420)  # estimativa ≈ 396: passa na guarda de entrada
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} teto real", "tipo": "quadrada",
                                                  "lado_m": 500.0,
                                                  "area_estudo": {"type": "Polygon",
                                                                  "coordinates": [externo, buraco]}})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        assert r.json()["ficha"]["contagem_esperada"] <= 420, "a estimativa já passava do teto; refazer o caso"
        with pytest.raises(FalhaDefinitiva) as e:
            amc_tarefas.amc_gerar_unidades(ContextoDeTeste(tenant), uuid.UUID(cid))
        assert "teto" in str(e.value)
        conjunto = sessao_a.get(f"/api/amc/conjuntos/{cid}").json()
        assert conjunto["estado"] == "falhou", conjunto["estado"]
        assert conjunto["n_unidades"] == 0 and conjunto["erro"]
        assert conjunto["ficha"]["recusado"] is True
        assert conjunto["ficha"]["n_unidades_geradas"] > 420, conjunto["ficha"]["n_unidades_geradas"]
        # e as unidades foram limpas de verdade, não só descontadas na ficha
        assert sessao_a.get(f"/api/amc/conjuntos/{cid}/unidades").json()["total"] == 0
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{cid}")
