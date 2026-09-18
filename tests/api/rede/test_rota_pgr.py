"""pgRouting instalado e conferido contra Dijkstra independente (portão literal do item
L2-11-c-rota-matriz-isocrona):

1. `SELECT pgr_version()` responde (extensão instalada no banco da plataforma);
2. `pgr_drivingDistance` sobre a rede de demonstração (`plat.rota_pgr_demo`, mesmo recorte OSM do
   serviço OSRM) confere com o Dijkstra de um networkx.DiGraph montado dos MESMOS custos, em 20
   origens sorteadas com semente fixa — mesmos conjuntos de nós alcançáveis e custos agregados
   batendo nó a nó (tolerância de ponto flutuante);
3. a isócrona pela rede (/api/isocrona-rede) devolve polígono coerente com o orçamento.

Se a rede não estiver carregada, o próprio teste a carrega pela carga oficial
(scripts/rota_pgr_demo_carga.py) — nunca pula: a cláusula é do portão.
"""

import random
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import shape

RAIZ = Path(__file__).resolve().parents[3]
CENTRO_GUARULHOS = [-46.5330, -23.4628]
ORCAMENTO_S = 600.0  # 10 min — mesmo da isócrona leve do test_rota.py


@pytest.fixture(scope="module")
def rede_pgr(env):
    """Conexão própria (a carga faz DELETE+COPY e COMMITA — não cabe no rollback da conexao_plat_app)
    com a rede garantida. Devolve (conexão, grafo networkx) montados uma vez por módulo."""
    import psycopg2

    from app.rede import pgr
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        if not pgr.rede_presente(cur):
            subprocess.run(
                [sys.executable, str(RAIZ / "scripts" / "rota_pgr_demo_carga.py")],
                check=True, capture_output=True, text=True,
            )
        assert pgr.rede_presente(cur)
        grafo = pgr.rede_para_networkx(cur)
    yield con, grafo
    con.close()


def test_pgr_version_instalada(rede_pgr):
    from app.rede import pgr

    con, _ = rede_pgr
    with con.cursor() as cur:
        versao = pgr.versao(cur)
    assert versao and versao[0].isdigit(), versao


def test_driving_distance_confere_com_networkx_em_20_origens(rede_pgr):
    from app.rede import pgr

    con, grafo = rede_pgr
    nos = sorted(grafo.nodes)
    rng = random.Random(20260918)
    origens = rng.sample(nos, 20)
    with con.cursor() as cur:
        for origem in origens:
            linhas = pgr.distancia_conducao(cur, origem, ORCAMENTO_S)
            pgr_custos = {l["node"]: l["agg_cost"] for l in linhas}
            nx_custos = nx.single_source_dijkstra_path_length(grafo, origem, cutoff=ORCAMENTO_S, weight="weight")
            # pgr inclui o nó de partida com custo 0; networkx também — os conjuntos têm de ser iguais
            assert set(pgr_custos) == set(nx_custos), (
                f"origem {origem}: {len(set(nx_custos) - set(pgr_custos))} nós só no networkx, "
                f"{len(set(pgr_custos) - set(nx_custos))} só no pgRouting"
            )
            for no, custo in nx_custos.items():
                assert abs(pgr_custos[no] - custo) < 1e-6, (origem, no, pgr_custos[no], custo)


def test_isocrona_rede_endpoint(sessao_a):
    r = sessao_a.post("/api/isocrona-rede", json={"ponto": CENTRO_GUARULHOS, "minutos": 10})
    assert r.status_code == 200, r.text
    corpo = r.json()
    poligono = shape(corpo["poligono"])
    assert poligono.area > 0
    assert corpo["nos_alcancaveis"] >= 3
    assert "pgr_drivingDistance" in corpo["metodo"]
    assert corpo["proveniencia"]["sha256"]
