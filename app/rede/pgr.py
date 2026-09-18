"""pgRouting sobre a rede de demonstração `plat.rota_pgr_demo` (item L2-11-c-rota-matriz-isocrona).

É a contraparte PostGIS do serviço OSRM: MESMO recorte OSM (osrm/guarulhos.osm.pbf, carregado por
scripts/rota_pgr_demo_carga.py), mesmo perfil de custo (segundos por classe de via). Serve para a
isócrona "pela rede do inquilino" do enunciado (pgr_drivingDistance + pgr_alphaShape) e para a prova
cruzada do portão (drivingDistance × Dijkstra independente em networkx — tests/api/rede/test_rota_pgr.py).

Este módulo só LÊ: a topologia (source/target de cada aresta) é montada na carga; as funções pgr_*
(pgr_version, pgr_drivingDistance, pgr_alphaShape) vivem no schema `public` da extensão pgRouting."""

import math

from app.schema_ambiente import esquemas_do_ambiente, reescrever_schema

# km/h por classe de via OSM, espelhando o car.lua do OSRM (profiles/car.lua do v5.25): a comparação
# OSRM × pgRouting do adversário só é justa se os dois motores partirem de custos parecidos.
VELOCIDADES_KMH = {
    "motorway": 90, "motorway_link": 45,
    "trunk": 85, "trunk_link": 40,
    "primary": 65, "primary_link": 30,
    "secondary": 55, "secondary_link": 30,
    "tertiary": 40, "tertiary_link": 25,
    "residential": 25, "unclassified": 25,
    "service": 15, "living_street": 10,
    "pedestrian": 5, "track": 15, "path": 5, "footway": 5, "cycleway": 15, "steps": 5,
}
VELOCIDADE_PADRAO_KMH = 25.0
M_POR_GRAU_LAT = 111_320.0


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def custos_s(highway: str | None, oneway: str | None, comprimento_m: float) -> tuple[float, float]:
    """(cost, reverse_cost) em segundos; -1 no sentido proibido pelo oneway do OSM."""
    v = VELOCIDADES_KMH.get((highway or "").strip(), VELOCIDADE_PADRAO_KMH)
    s = comprimento_m / (v * 1000 / 3600)
    o = (oneway or "").strip().lower()
    if o in ("yes", "true", "1"):
        return s, -1.0
    if o == "-1":
        return -1.0, s
    return s, s


_SQL_ARESTAS = "SELECT id, source, target, cost, reverse_cost FROM plat.rota_pgr_demo"


def _arestas_sql() -> str:
    """O SQL das arestas viaja como PARÂMETRO das funções pgr_* (que o executam por SPI), e o cursor só
    reescreve o texto da consulta principal — o parâmetro precisa da reescrita explícita do schema."""
    schema, trabalho = esquemas_do_ambiente()
    return reescrever_schema(_SQL_ARESTAS, schema, trabalho)


def versao(cur) -> str:
    cur.execute("SELECT pgr_version() AS v")
    return cur.fetchone()["v"]


def rede_presente(cur) -> bool:
    cur.execute("SELECT count(*) AS n FROM plat.rota_pgr_demo")
    return cur.fetchone()["n"] > 0


def vertice_mais_proximo(cur, lon: float, lat: float) -> int:
    cur.execute(
        """
        SELECT v.id FROM plat.rota_pgr_demo_vertices_pgr v
        WHERE EXISTS (SELECT 1 FROM plat.rota_pgr_demo a WHERE a.source = v.id OR a.target = v.id)
        ORDER BY v.the_geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1
        """,
        (lon, lat),
    )
    linha = cur.fetchone()
    if linha is None:
        raise ValueError("rede de demonstração vazia (rode scripts/rota_pgr_demo_carga.py)")
    return linha["id"]


def distancia_conducao(cur, origem_id: int, max_s: float) -> list[dict]:
    """pgr_drivingDistance dirigido a partir de um vértice: todos os nós alcançáveis em `max_s`."""
    cur.execute(
        "SELECT node, cost, agg_cost FROM pgr_drivingDistance(%s, %s, %s, true)",
        (_arestas_sql(), origem_id, max_s),
    )
    return list(cur.fetchall())


# teto de segurança medido nesta máquina (18/09/2026): pgr_alphaShape (pgRouting 3.6, assinatura nova
# geometry+alpha) responde em segundos até ~19 mil nós; com ~89 mil nós (isócrona de 10 min do recorte)
# derrubou o backend do Postgres (crash-recovery automático). Acima do teto o casco sai por
# shapely.concave_hull — mesmo motor do /api/isocrona (OSRM), mesma resposta.
PGR_ALPHASHAPE_MAX_NOS = 15_000
PGR_ALPHASHAPE_ALPHA = 1.5


def isocrona_poligono(cur, lon: float, lat: float, minutos: float) -> dict | None:
    """Isócrona pela REDE (não por grade): pgr_drivingDistance até o orçamento, casco por
    pgr_alphaShape quando o conjunto cabe no teto medido (senão shapely.concave_hull).
    Devolve GeoJSON ou None se menos de 3 nós alcançáveis."""
    origem = vertice_mais_proximo(cur, lon, lat)
    alcancaveis = distancia_conducao(cur, origem, minutos * 60.0)
    if len(alcancaveis) < 3:
        return None
    ids = [a["node"] for a in alcancaveis]

    if len(ids) <= PGR_ALPHASHAPE_MAX_NOS:
        # alphaShape devolve GeometryCollection de polígonos/linhas/pontos: fica o maior polígono
        cur.execute(
            """
            WITH c AS (
              SELECT pgr_alphaShape(ST_Collect(v.the_geom), %s) AS g
              FROM plat.rota_pgr_demo_vertices_pgr v WHERE v.id = ANY(%s)
            ),
            d AS (SELECT (ST_Dump(g)).geom AS geom FROM c)
            SELECT ST_AsGeoJSON(geom)::json AS geojson
            FROM d WHERE GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')
            ORDER BY ST_Area(geom::geography) DESC LIMIT 1
            """,
            (PGR_ALPHASHAPE_ALPHA, ids),
        )
        geojson = cur.fetchone()["geojson"]
        metodo = "pgr_drivingDistance + pgr_alphaShape (pgRouting)"
    else:
        from shapely import MultiPoint, concave_hull
        from shapely.geometry import mapping

        cur.execute(
            "SELECT v.x, v.y FROM plat.rota_pgr_demo_vertices_pgr v WHERE v.id = ANY(%s)",
            (ids,),
        )
        mp = MultiPoint([(r["x"], r["y"]) for r in cur.fetchall()])
        geojson = mapping(concave_hull(mp, ratio=0.3, allow_holes=False))
        metodo = "pgr_drivingDistance + shapely.concave_hull (conjunto acima do teto medido do pgr_alphaShape)"

    return {
        "poligono": geojson,
        "nos_alcancaveis": len(ids),
        "origem_vertice": origem,
        "metodo": metodo,
    }


def rede_para_networkx(cur) -> "object":
    """Grafo networkx.DiGraph com os MESMOS custos da tabela (a prova do portão: Dijkstra
    independente confere com pgr_drivingDistance)."""
    import networkx as nx

    cur.execute(_SQL_ARESTAS)
    g = nx.DiGraph()
    for a in cur.fetchall():
        if a["cost"] is not None and a["cost"] >= 0:
            g.add_edge(a["source"], a["target"], weight=a["cost"])
        if a["reverse_cost"] is not None and a["reverse_cost"] >= 0:
            g.add_edge(a["target"], a["source"], weight=a["reverse_cost"])
    return g
