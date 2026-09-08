"""Cláusulas MEDIDAS do item L2-04-i-wms-wmts-sld (lentas, arquivo separado do funcional):

- `GetMap` vetorial 1024x768 com a camada quente e com a camada fria (primeiro pedido da tabela, sem
  cache de banco nem de estilo): p95 gravado em `tests/medidas/L2-04-i-wms-wmts-sld.json`;
- WMTS PRÉ-RENDERIZADO de uma camada de 100 mil feições: o job `wmts.publicar` gera o PMTiles raster,
  grava no bucket do inquilino, e o `GetTile` passa a servir daquele arquivo por leitura de FAIXA
  (`Range`) — o teste confere o cabeçalho `X-Plat-Origem`, compara com o desenho ao vivo e mede
  tempo de geração, tamanho e latência por tile.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_ogc_features_crs_cql2 import _criar_com_retentativa
from tests.api.test_rls import contexto, ids_por_slug
from tests.api.test_wms_wmts import _imagem, _wms, _wmts

ITEM = "L2-04-i-wms-wmts-sld"
N = 100_000
# faixa compacta do sudeste: mantém o número de tiles de z0-z14 na casa das centenas
OESTE, SUL, LESTE, NORTE = -47.0, -22.0, -46.5, -21.5
SRID = 4674
Z_MIN, Z_MAX = 0, 14


@pytest.fixture(scope="module")
def conexao_carga(env):
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        yield con
    finally:
        con.rollback()
        con.close()


@pytest.fixture(scope="module")
def camada_100k(conexao_carga):
    fabrica = FabricaCamada(conexao_carga)
    ids = ids_por_slug(conexao_carga)
    admin_id = _admin_usuario_id(conexao_carga, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_carga, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"}],
        geometria="Point")
    contexto(conexao_carga, ids["demo"], usuario_id=admin_id, login="admin")
    t0 = time.perf_counter()
    with conexao_carga.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (geom, nome, categoria) '
            "SELECT ST_SetSRID(ST_MakePoint(%s + (i %% 1000) * %s, %s + (i / 1000) * %s), %s), "
            "'P' || i, (ARRAY['A','B','C'])[1 + i %% 3] FROM generate_series(1, %s) i",
            (OESTE, (LESTE - OESTE) / 1000.0, SUL, (NORTE - SUL) / 100.0, SRID, N))
        cur.execute(f'ANALYZE "{dados["schema"]}"."{dados["tabela"]}"')
    conexao_carga.commit()
    yield {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id,
           "semeadura_s": round(time.perf_counter() - t0, 2), "con": conexao_carga}
    fabrica.limpar()


def _p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(len(xs) * 0.95) - 1))]


def test_medida_getmap_1024x768_quente_e_frio(sessao_a, camada_100k, medida):
    cid = camada_100k["id"]
    caixa = f"{OESTE},{SUL},{LESTE},{NORTE}"
    comum = {"request": "GetMap", "layers": cid, "styles": "", "crs": "CRS:84", "bbox": caixa,
             "width": 1024, "height": 768, "format": "image/png", "transparent": "true"}
    # FRIO: primeiro pedido desta camada neste processo (nada em cache de plano, de estilo ou de página)
    t0 = time.perf_counter()
    r = _wms(sessao_a, cid, **comum)
    frio_ms = (time.perf_counter() - t0) * 1000
    img = _imagem(r)
    assert img.size == (1024, 768)
    assert int(r.headers["x-plat-feicoes"]) > 1000
    quentes = []
    for k in range(12):                       # move um pouco a caixa para não medir cache de resposta
        d = 0.002 * k
        p = {**comum, "bbox": f"{OESTE + d},{SUL + d},{LESTE + d},{NORTE + d}"}
        t = time.perf_counter()
        rr = _wms(sessao_a, cid, **p)
        quentes.append((time.perf_counter() - t) * 1000)
        assert rr.status_code == 200
    p95 = _p95(quentes)
    gravar = medida(ITEM)
    gravar("getmap_1024x768_quente_p95_ms", round(p95, 1), "ms",
           "12 GetMap 1024x768 seguidos sobre camada de 100 mil pontos (TestClient em processo), caixa "
           "deslocada a cada pedido; p95")
    gravar("getmap_1024x768_quente_mediana_ms", round(sorted(quentes)[len(quentes) // 2], 1), "ms",
           "mesma medida, mediana")
    gravar("getmap_1024x768_frio_ms", round(frio_ms, 1), "ms",
           "primeiro GetMap da camada no processo (sem plano de consulta nem estilo em cache)")
    gravar("carga_1min", round(os.getloadavg()[0], 2), "load", "os.getloadavg()[0] no instante da medida")
    gravar("semeadura_100k_s", camada_100k["semeadura_s"], "s",
           "INSERT ... generate_series(1, 100000) + ANALYZE na trilha")
    assert frio_ms <= 4000, f"frio {frio_ms:.0f} ms acima do teto de 4.000 ms"
    assert p95 <= 1500, f"quente p95 {p95:.0f} ms acima do teto de 1.500 ms"


def test_wmts_prerenderizado_z0_z14_de_100_mil_feicoes(sessao_a, camada_100k, medida):
    """Gera o PMTiles com o job real (mesma função que o worker chama), serve por Range e compara com
    o desenho ao vivo."""
    from app.jobs import contexto_job as cj
    from app.ogc_mapas import matrizes, prerenderizado
    from app.ogc_mapas.tarefas import wmts_publicar

    cid = camada_100k["id"]
    job = {"id": str(uuid.uuid4()), "tenant_id": camada_100k["tenant_id"],
           "usuario_id": camada_100k["admin_id"], "tipo": "wmts.publicar", "tentativa": 1}
    ctx = cj.ContextoJob(job, Path("/tmp"), "teste-l204i")
    # o corpo da tarefa só usa `db()`, `progresso()` e `job_id`; aqui não há linha em `plat.job` (isso é do
    # worker do L0-05, com teste próprio), então o progresso vira registro em memória em vez de heartbeat
    passos: list = []
    ctx.progresso = lambda pct, msg="": passos.append((pct, msg))
    t0 = time.perf_counter()
    resumo = wmts_publicar(ctx, item_id=uuid.UUID(cid), z_min=Z_MIN, z_max=Z_MAX)
    duracao_s = time.perf_counter() - t0
    assert resumo["tiles"] > 0 and resumo["bytes"] > 0
    gravar = medida(ITEM)
    gravar("wmts_prerender_z0_z14_s", round(duracao_s, 1), "s",
           f"job wmts.publicar em camada de {N} pontos, z{Z_MIN}-z{Z_MAX} sobre a extensão da camada")
    gravar("wmts_prerender_tiles", resumo["tiles"], "tiles", "tiles com feição gravados no PMTiles")
    gravar("wmts_prerender_bytes", resumo["bytes"], "bytes", "tamanho do arquivo PMTiles no bucket")
    gravar("wmts_prerender_tiles_vazios", resumo["tiles_vazios"], "tiles",
           "tiles sem nenhuma feição (não entram no arquivo)")
    # o tile agora vem do arquivo, por leitura de faixa
    caixa3857 = prerenderizado._para_3857((OESTE, SUL, LESTE, NORTE))
    x, y = matrizes.tiles_da_caixa(caixa3857, 12)[0]
    tempos = []
    for _ in range(10):
        t = time.perf_counter()
        r = _wmts(sessao_a, cid, request="GetTile", layer=cid, style="padrao",
                  tilematrixset="GoogleMapsCompatible", tilematrix="12", tilerow=y, tilecol=x,
                  format="image/png")
        tempos.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("x-plat-origem") == "prerenderizado", r.headers
    img = _imagem(r)
    assert img.size == (256, 256)
    gravar("wmts_tile_prerenderizado_p95_ms", round(_p95(tempos), 1), "ms",
           "GetTile z12 servido do PMTiles por Range (10 pedidos, TestClient em processo)")
    # fora da faixa publicada o serviço volta a desenhar ao vivo, sem erro
    fora = _wmts(sessao_a, cid, request="GetTile", layer=cid, style="padrao",
                 tilematrixset="GoogleMapsCompatible", tilematrix="16", tilerow=y * 16, tilecol=x * 16,
                 format="image/png")
    assert fora.status_code == 200 and fora.headers.get("x-plat-origem") == "vivo"
    # e a publicação está descrita para o GetCapabilities
    with camada_100k["con"].cursor() as cur:
        contexto(camada_100k["con"], camada_100k["tenant_id"], usuario_id=camada_100k["admin_id"], login="admin")
        pub = prerenderizado.descricao(cur, cid)
    assert pub and pub["z_min"] == Z_MIN and pub["z_max"] == Z_MAX and pub["tiles"] == resumo["tiles"]
    assert passos and passos[-1][0] == 100
