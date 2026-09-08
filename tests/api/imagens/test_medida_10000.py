"""Cláusula 6 do item L1-01-a: 10.000 itens sintéticos, busca por bbox medida e gravada em
tests/medidas/L1-01-a.json (`PLAT_GRAVAR_MEDIDAS=1`). Ingestão em massa por `pgstac.create_items` (mesma
função que uma ingestão em lote real usaria, item L1-01-h) + espelho em massa em `plat.raster_item`;
a MEDIÇÃO em si é a chamada HTTP completa (FastAPI + pgstac.search), não um atalho direto ao SQL."""

import time

import pytest

from app import db, limites
from app.imagens import pgstac as ps
from app.imagens import raster_item as ri

N_ITENS = 10_000
# Brasil aproximado; a caixa de busca abaixo é ~1/16 da área total, o bastante para provar que o índice
# espacial do pgstac filtra (não é "buscar tudo e devolver tudo").
BBOX_TOTAL = (-73.0, -33.0, -35.0, 5.0)
BBOX_BUSCA = (-55.0, -17.0, -45.0, -9.0)


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def colecao_10k(token_stac_a, tenant_id_a, env):
    """Semeia 10.000 itens sintéticos direto no banco (como plat_app, mesmo papel/contexto que a API usa —
    não como postgres): ingestão em massa é responsabilidade de um item futuro (L1-01-h), aqui só se prova
    que o catálogo AGUENTA o volume e que a busca por bbox permanece rápida."""
    ctx = db.Contexto(tenant_id_a, 0, "zt-medida")
    colecao_id = ps.nome_colecao(tenant_id_a, "medida10k")
    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id_a, colecao_id) is None:
            ps.colecao_criar(cur, tenant_id_a, "medida10k", {})

    xmin, ymin, xmax, ymax = BBOX_TOTAL
    lado = int(N_ITENS**0.5) + 1  # grade regular, determinística — reproduzível sem estado aleatório
    itens = []
    for i in range(N_ITENS):
        gx, gy = i % lado, i // lado
        lon = xmin + (xmax - xmin) * (gx / lado)
        lat = ymin + (ymax - ymin) * (gy / lado)
        itens.append(
            {
                "type": "Feature",
                "stac_version": "1.0.0",
                "id": f"m10k-{i:06d}",
                "collection": colecao_id,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "bbox": [lon, lat, lon, lat],
                "properties": {"datetime": f"202{i % 6}-{(i % 12) + 1:02d}-01T00:00:00Z"},
                "assets": {},
                "links": [],
            }
        )
    with db.db(ctx) as cur:
        cur.execute("SELECT count(*) AS n FROM pgstac.items WHERE collection = %s", (colecao_id,))
        ja = cur.fetchone()["n"]
        if ja < N_ITENS:
            LOTE = 1000
            for i in range(0, len(itens), LOTE):
                ps.itens_criar_lote(cur, colecao_id, itens[i : i + LOTE])
                ri.espelhar_lote(cur, tenant_id_a, colecao_id, [it["id"] for it in itens[i : i + LOTE]])
        # `pgstac` é infraestrutura GLOBAL da máquina (compartilhada por TODAS as trilhas; ver
        # db/pgstac_instalar.sh) enquanto `plat.raster_item` vive no schema PRÓPRIO desta trilha — uma
        # base de trilha recriada do zero (`trilha_ambiente.sh`) herda os itens que outra rodada já
        # deixou no pgstac para esta MESMA coleção sintética, mas começa com `raster_item` vazio. Sem
        # este espelhamento de reconciliação a asserção de contagem do espelho falharia por um motivo
        # de higiene do ambiente de teste, não por um defeito do código: sempre alinhar o espelho aos
        # itens que já existem no pgstac desta coleção, nunca assumir que os dois nasceram juntos.
        cur.execute(
            "SELECT count(*) AS n FROM plat.raster_item WHERE tenant_id = %s AND colecao = %s",
            (tenant_id_a, colecao_id),
        )
        if cur.fetchone()["n"] < N_ITENS:
            cur.execute("SELECT id FROM pgstac.items WHERE collection = %s", (colecao_id,))
            todos_ids = [r["id"] for r in cur.fetchall()]
            LOTE = 1000
            for i in range(0, len(todos_ids), LOTE):
                ri.espelhar_lote(cur, tenant_id_a, colecao_id, todos_ids[i : i + LOTE])
    return colecao_id


def test_10000_itens_carregados(colecao_10k, tenant_id_a):
    ctx = db.Contexto(tenant_id_a, 0, "zt-medida")
    with db.db(ctx) as cur:
        cur.execute("SELECT count(*) AS n FROM pgstac.items WHERE collection = %s", (colecao_10k,))
        assert cur.fetchone()["n"] == N_ITENS
        cur.execute(
            "SELECT count(*) AS n FROM plat.raster_item WHERE tenant_id = %s AND colecao = %s",
            (tenant_id_a, colecao_10k),
        )
        assert cur.fetchone()["n"] == N_ITENS


def test_busca_por_bbox_medida(colecao_10k, token_stac_a, medida):
    c = _cliente()
    tok = token_stac_a["token"]
    bbox_txt = ",".join(str(x) for x in BBOX_BUSCA)
    url = f"/svc/{tok}/stac/search?collections={colecao_10k}&bbox={bbox_txt}&limit={limites.STAC_PAGINA_MAX}"

    # 1ª chamada fora do relógio: aquece o plano/estatística do `pgstac.search` (search_wheres), como
    # qualquer índice recém-populado — a medição que fica é da consulta em regime normal.
    r0 = c.get(url)
    assert r0.status_code == 200, r0.text

    NUM_CHAMADAS = 5
    tempos = []
    total_encontrado = None
    for _ in range(NUM_CHAMADAS):
        t0 = time.perf_counter()
        r = c.get(url)
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, r.text
        corpo = r.json()
        total_encontrado = corpo.get("numberMatched", len(corpo["features"]))

    tempos.sort()
    mediana_ms = tempos[len(tempos) // 2]

    # a caixa de busca cobre 1/4 x 1/4 = 1/16 da grade total -> ~625 dos 10.000 pontos
    esperado = N_ITENS / 16
    assert abs(total_encontrado - esperado) / esperado < 0.15, (total_encontrado, esperado)

    comando = (
        f"GET /svc/<token>/stac/search?collections=<tenant>-medida10k&bbox={bbox_txt}"
        f"&limit={limites.STAC_PAGINA_MAX}  (10.000 itens sintéticos previamente carregados na coleção; "
        f"mediana de {NUM_CHAMADAS} chamadas HTTP completas, 1ª chamada de aquecimento descartada)"
    )
    medida("L1-01-a")("busca_bbox_10000_itens_mediana_ms", round(mediana_ms, 2), "ms", comando)
    medida("L1-01-a")("busca_bbox_itens_encontrados", int(total_encontrado), "itens", comando)
    medida("L1-01-a")("busca_bbox_itens_no_catalogo", N_ITENS, "itens", comando)
