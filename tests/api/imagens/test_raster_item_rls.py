"""RLS de `plat.raster_item` (item L1-01-a, cláusula 5): a tabela-espelho é fonte de autorização própria,
independente do filtro por nome de coleção do pgstac. Prova em dois níveis: (1) a API espelha a escrita
(POST item -> linha aparece só para o dono); (2) SQL direto como `plat_app`, trocando `plat.tenant_id` de
sessão como o `contexto_anonimo`/`db.db(ctx)` fazem — sem RLS, o SELECT do inquilino B veria a linha de A."""

import secrets

from tests.api.imagens.conftest import item_stac


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


def test_post_item_espelha_em_raster_item_do_dono(token_stac_a, tenant_id_a, conexao_plat_app):
    c = _cliente()
    tok = token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/collections", params={"slug": f"espelho-{secrets.token_hex(4)}"}, json={})
    assert r.status_code == 201, r.text
    colecao = r.json()["id"]
    item = item_stac("item-espelho-1", colecao)
    ri = c.post(
        f"/svc/{tok}/stac/collections/{colecao}/items", json={**item, "raster": {"sha256": "a" * 64, "bytes": 123}}
    )
    assert ri.status_code == 201, ri.text
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id_a),))
        cur.execute(
            "SELECT * FROM plat.raster_item WHERE tenant_id = %s AND colecao = %s AND item_id = %s",
            (tenant_id_a, colecao, "item-espelho-1"),
        )
        linha = cur.fetchone()
    assert linha is not None
    assert linha["sha256"] == "a" * 64 and linha["bytes"] == 123 and linha["estado"] == "ativo"


def test_rls_tenant_b_nao_ve_linha_de_a_no_raster_item(token_stac_a, tenant_id_a, tenant_id_b, conexao_plat_app):
    c = _cliente()
    tok = token_stac_a["token"]
    r = c.post(f"/svc/{tok}/stac/collections", params={"slug": f"rlsdireto-{secrets.token_hex(4)}"}, json={})
    assert r.status_code == 201, r.text
    colecao = r.json()["id"]
    ri = c.post(f"/svc/{tok}/stac/collections/{colecao}/items", json=item_stac("item-rls-1", colecao))
    assert ri.status_code == 201, ri.text

    with conexao_plat_app.cursor() as cur:
        # como o inquilino B veria: troca só o GUC de sessão, exatamente como app/catalogo/comum.contexto_anonimo
        # e app/db.py:_preparar fazem por trás de auth.contexto() — sem RLS isto veria a linha de A.
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id_b),))
        cur.execute(
            "SELECT * FROM plat.raster_item WHERE colecao = %s AND item_id = %s", (colecao, "item-rls-1")
        )
        assert cur.fetchone() is None, "RLS falhou: B enxergou uma linha de A em plat.raster_item"

        # confere que ela EXISTE (não é um falso-negativo por outro motivo) trocando de volta para A
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id_a),))
        cur.execute(
            "SELECT * FROM plat.raster_item WHERE colecao = %s AND item_id = %s", (colecao, "item-rls-1")
        )
        assert cur.fetchone() is not None


def test_rls_bloqueia_insert_com_tenant_id_de_outro(tenant_id_a, tenant_id_b, conexao_plat_app):
    """`WITH CHECK` da política: mesmo que o código tentasse gravar um tenant_id que não é o da sessão
    corrente, o INSERT é recusado pelo Postgres, não só pelo Python."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id_a),))
        try:
            cur.execute(
                "INSERT INTO plat.raster_item (tenant_id, colecao, item_id) VALUES (%s, %s, %s)",
                (tenant_id_b, f"{tenant_id_b}-x", "item-x"),
            )
            cur.connection.commit()
            falhou = False
        except Exception:
            cur.connection.rollback()
            falhou = True
        assert falhou, "RLS falhou: plat_app inseriu linha com tenant_id de outro inquilino"


def test_check_colecao_tem_de_comecar_pelo_tenant_id(tenant_id_a, conexao_plat_app):
    """O CHECK de `colecao` (migração 20260906T1901) é defesa em profundidade: mesmo sob o tenant_id certo,
    uma coleção que não comece por `<tenant_id>-` é recusada pelo banco."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(tenant_id_a),))
        try:
            cur.execute(
                "INSERT INTO plat.raster_item (tenant_id, colecao, item_id) VALUES (%s, %s, %s)",
                (tenant_id_a, "outro-prefixo-x", "item-y"),
            )
            cur.connection.commit()
            falhou = False
        except Exception:
            cur.connection.rollback()
            falhou = True
        assert falhou, "CHECK falhou: aceitou coleção sem o prefixo <tenant_id>-"
