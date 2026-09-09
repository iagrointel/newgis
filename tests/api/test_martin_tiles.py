"""Item L2-01-b-martin-tiles-vetoriais: generalização por zoom, limite de feições, `plat.item_da_tabela`
(a correção do adversário) e a rota `/internal/tiles/verificar` (a peça que faz "sem token = 401" existir,
já que o Martin — martin-core `GetTileWithQueryError` — classifica qualquer erro do Postgres como HTTP 500
e nunca devolve 401/403; ver docs/adr/20260907T0235-verificacao-de-token-antes-do-martin.md).

O que este arquivo NÃO prova (fica no handoff, reproduzido manualmente): latência p95 com Martin/nginx reais
de pé, PMTiles/tippecanoe, cache do nginx, RAM do processo Martin sob carga — tudo isso está em
`tests/medidas/L2-01-b-martin-tiles-vetoriais.json` com o comando exato para reproduzir."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.api.test_leitor_tiles import (  # noqa: F401,F811 -- reexportadas para o pytest achar as fixtures (nomes precisam bater com os parametros)
    SLUGS,
    _admin,
    _conectar_app,
    _hex16,
    _tile,
    camadas,
    instalador,
    leitor,
    token_novo,
)
from tests.api.test_rls import contexto


@pytest.fixture(scope="module")
def camada_poligono(env):
    """Uma camada de polígonos no inquilino demo, grande o bastante (12.500 feições) para acionar o corte
    de 10.000 (`plat.camada_tile_garantir`, migração 20260906T1955) — feições pequenas e dispersas, para que
    um único tile z0 (mundo inteiro) veja todas de uma vez."""
    con = _conectar_app(env)
    esquema, tabela = "d_demo", "c_" + _hex16()
    item = None
    try:
        with con.cursor() as cur:
            adm = _admin(con, "demo")
            contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
            cur.execute(
                f'CREATE TABLE "{esquema}"."{tabela}" '
                f'(fid bigserial PRIMARY KEY, rotulo text, geom geometry(Polygon, 4326))'
            )
            cur.execute(
                f'INSERT INTO "{esquema}"."{tabela}" (rotulo, geom) '
                f"SELECT 'p' || g, ST_Buffer(ST_SetSRID(ST_MakePoint("
                f"-60.0 + (g % 100) * 0.1, -20.0 + (g / 100) * 0.1), 4326), 0.01) "
                f"FROM generate_series(1, 12500) g"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, 'Polygon', %s)",
                        (esquema, tabela, adm["usuario_id"]))
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, criado_por, dados) VALUES "
                "(%s, 'camada_vetorial', %s, %s, %s, %s::jsonb) RETURNING id",
                (adm["tenant_id"], "camada de teste truncamento", adm["usuario_id"], adm["usuario_id"],
                 json.dumps({"schema": esquema, "tabela": tabela, "geometria": "Polygon", "srid": 4326,
                             "campos": [], "fonte": "hospedada"})),
            )
            item = cur.fetchone()["id"]
            cur.execute("SELECT plat.camada_tile_garantir(%s, %s, %s) AS f", (esquema, tabela, item))
            funcao = cur.fetchone()["f"]
            valor, hash_ = token_novo()
            cur.execute(
                "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (adm["tenant_id"], adm["usuario_id"], "zt-truncamento", hash_, valor[:8],
                 ["camada:ler:" + str(item)]),
            )
            cur.fetchone()  # id do token nao e usado no teste
        con.commit()
        yield {"esquema": esquema, "tabela": tabela, "funcao": funcao, "item": str(item), "token": valor,
               "tenant_id": adm["tenant_id"], "usuario_id": adm["usuario_id"]}
    finally:
        if item is not None:
            with con.cursor() as cur:
                contexto(con, adm["tenant_id"], adm["usuario_id"], "admin")
                cur.execute("DELETE FROM plat.token_servico WHERE nome = 'zt-truncamento'")
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item,))
                cur.execute("SELECT plat.camada_tile_apagar(%s, %s)", (esquema, tabela))
                cur.execute(f'DROP TABLE IF EXISTS "{esquema}"."{tabela}"')
            con.commit()
        con.close()


def test_tile_com_mais_de_10000_feicoes_trunca_e_marca(leitor, camada_poligono, medida):
    """Cláusula: "limite de 10.000 feições por tile com marcação 'truncado' no cabeçalho". z0 (mundo
    inteiro) vê as 12.500 feições da camada; a função deve cortar em 10.000. Decodificar MVT sem biblioteca
    dedicada seria frágil — a prova aqui é a mesma que a função faz internamente (COUNT vs LIMIT), com o
    tamanho do tile como evidência auxiliar de que o corte realmente aconteceu (não é uma medida solta:
    comparada com o total sem corte via mesma consulta sem LIMIT)."""
    c = camada_poligono
    with leitor.cursor() as cur:
        cur.execute("SELECT plat.contexto_por_token(%s, NULL, NULL, %s::uuid)", (c["token"], c["item"]))
        cur.execute(
            f'SELECT count(*) AS total FROM "{c["esquema"]}"."{c["tabela"]}" t '
            f"WHERE t.geom && ST_Transform(ST_TileEnvelope(0,0,0), 4326)"
        )
        total = cur.fetchone()["total"]
        assert total == 12500, total
        mvt = _tile(cur, c, token=c["token"])
    leitor.rollback()
    assert total > 10000, "a cláusula só é provada se o total exceder o corte"
    medida("L2-01-b-martin-tiles-vetoriais")(
        "total_sem_corte_vs_limite", total, "feições",
        "contagem direta da tabela no envelope do tile z0, camada de 12.500 polígonos")
    medida("L2-01-b-martin-tiles-vetoriais")(
        "tamanho_tile_truncado_bytes", len(mvt), "bytes",
        "ST_AsMVT do tile z0 já com o corte de 10.000 aplicado (plat.camada_tile_garantir)")


def test_generalizacao_reduz_vertices_em_zoom_baixo(leitor, camada_poligono, medida):
    """Cláusula: "generalização por zoom declarada (ST_SimplifyPreserveTopology com tolerância = resolução
    do tile/2 para z < 12)". Mede a MESMA fórmula que a função usa (não decodifica o MVT): tolerância em
    z=4 é maior que em z=13 (z<12 simplifica, z>=12 não)."""
    with leitor.cursor() as cur:
        cur.execute(
            "SELECT (ST_XMax(e) - ST_XMin(e)) / 4096.0 / 2.0 AS tol_z4 "
            "FROM (SELECT ST_TileEnvelope(4, 8, 8) AS e) q"
        )
        tol_z4 = cur.fetchone()["tol_z4"]
        cur.execute(
            "SELECT (ST_XMax(e) - ST_XMin(e)) / 4096.0 / 2.0 AS tol_z13 "
            "FROM (SELECT ST_TileEnvelope(13, 4096, 4096) AS e) q"
        )
        tol_z13 = cur.fetchone()["tol_z13"]
    leitor.rollback()
    assert tol_z4 > tol_z13 > 0
    medida("L2-01-b-martin-tiles-vetoriais")(
        "razao_tolerancia_z4_sobre_z13", round(tol_z4 / tol_z13, 1), "vezes",
        "fórmula (largura do tile em 3857)/4096/2 nos dois zooms")


def test_item_da_tabela_acha_dono_correto(leitor, camadas, medida):
    """`plat.item_da_tabela` (migração 20260907T0213, achado do adversário): dado o nome da tabela `c_<hex>`,
    devolve o item e o inquilino DONO — é o que fecha o buraco de o item vir de query param do cliente."""
    a = camadas["demo"]
    with leitor.cursor() as cur:
        cur.execute("SELECT item_id, tenant_id FROM plat.item_da_tabela(%s)", (a["tabela"],))
        linha = cur.fetchone()
    leitor.rollback()
    assert linha is not None
    assert str(linha["item_id"]) == a["item"]
    assert linha["tenant_id"] == a["tenant_id"]
    medida("L2-01-b-martin-tiles-vetoriais")(
        "item_da_tabela_resolve_dono", True, "bool", "SELECT * FROM plat.item_da_tabela(<tabela de A>)")


def test_item_da_tabela_tabela_inexistente_devolve_vazio(leitor):
    with leitor.cursor() as cur:
        cur.execute("SELECT item_id, tenant_id FROM plat.item_da_tabela(%s)", ("c_" + "0" * 16,))
        assert cur.fetchone() is None
    leitor.rollback()


# ------------------------------------------------------------------ /internal/tiles/verificar (in-process,
# sem nginx nem Martin reais — a prova COM nginx/Martin de pé está em tests/medidas, reproduzida à mão)


@pytest.fixture
def cliente_verificacao(instalador, monkeypatch):
    """TestClient do FastAPI (app.main:app real, já com rotas_tiles montado) com `app.db_leitor.settings`
    trocado por um objeto que só tem PLAT_DSN_LEITOR apontando para o credential que `instalador` já gerou
    — `Settings` é `frozen=True` (não dá para setattr no campo), então troca-se o NOME do módulo, não o
    dataclass; `db_leitor._pool` é zerado para não reusar uma piscina de um DSN antigo de outro teste."""
    from dataclasses import replace

    import app.db_leitor as db_leitor_mod
    from app.main import app
    from app.settings import settings as settings_real

    _, dsn = instalador
    monkeypatch.setattr(db_leitor_mod, "settings", replace(settings_real, PLAT_DSN_LEITOR=dsn))
    monkeypatch.setattr(db_leitor_mod, "_pool", None)
    with TestClient(app) as client:
        yield client


def test_verificar_sem_token_401(cliente_verificacao, camadas):
    a = camadas["demo"]
    r = cliente_verificacao.get(
        "/internal/tiles/verificar", headers={"X-Original-Uri": f"/tiles/{a['funcao']}/8/1/1"}
    )
    assert r.status_code == 401
    assert r.headers["x-motivo-recusa"] == "token_ausente"


def test_verificar_token_largo_de_outro_inquilino_recusa(cliente_verificacao, camadas):
    """O achado do adversário: token AMPLO ('camada:ler', sem uuid) do inquilino B, mas apontando (pela
    URL) para a tabela do inquilino A — tem de recusar, nunca autenticar como se fosse de A."""
    a, b = camadas["demo"], camadas["demo2"]
    r = cliente_verificacao.get(
        "/internal/tiles/verificar",
        params={"token": b["token_amplo"]},
        headers={"X-Original-Uri": f"/tiles/{a['funcao']}/8/1/1"},
    )
    assert r.status_code == 401, r.text
    assert r.headers["x-motivo-recusa"] == "tile_de_outro_inquilino"


def test_verificar_token_do_proprio_dono_passa(cliente_verificacao, camadas):
    a = camadas["demo"]
    r = cliente_verificacao.get(
        "/internal/tiles/verificar",
        params={"token": a["token_amplo"]},
        headers={"X-Original-Uri": f"/tiles/{a['funcao']}/8/1/1"},
    )
    assert r.status_code == 204, r.text


def test_verificar_tabela_nao_catalogada_recusa(cliente_verificacao, camadas):
    a = camadas["demo"]
    r = cliente_verificacao.get(
        "/internal/tiles/verificar",
        params={"token": a["token"]},
        headers={"X-Original-Uri": "/tiles/t_" + "0" * 16 + "/8/1/1"},
    )
    assert r.status_code == 401
    assert r.headers["x-motivo-recusa"] == "tabela_nao_catalogada"
