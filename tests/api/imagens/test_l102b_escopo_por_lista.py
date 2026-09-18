"""Item L1-02-b (`token de serviço com escopo por LISTA`) — conserto de 17/09/2026 e o par que o prova.

O adversário de linha L1 (T9) achou que `escopo por lista` não alcançava item de IMAGEM: o vocabulário
de `app/auth/escopos.py` só aceitava `tiles:ler:<uuid>` no formato estrito 8-4-4-4-12, e o id de um item
STAC é uma string livre da fonte (`item-nao-uuid-1` na própria suíte da casa, `S2B_MSIL2A_...` numa cena
Sentinel-2 de verdade). Para esses itens `POST /api/tokens` recusava por VOCABULÁRIO, antes mesmo de
checar posse — e a única forma de servir o tile por token era um escopo LARGO (`tiles:ler` sem lista ou
`imagens:ler`), o oposto do que o item promete.

Conserto: `ID_ITEM` em `app/auth/escopos.py` (uuid OU id de item STAC, sem `:`, até 128 caracteres) e
`pgstac.item_existe_no_tenant` para a checagem de posse na criação do token.

Este arquivo é o PAR que o portão exige: recusa provada E a permissão legítima provada. Um teste de
recusa sozinho passaria com a rota quebrada para todo mundo.
"""

from __future__ import annotations

import secrets

import pytest

from tests.api.imagens.conftest import item_stac


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_nao_uuid(tenant_id_a):
    """Um item raster SERVÍVEL cujo id STAC não é uuid. Reusa os bytes do COG que `semear_raster` já
    subiu (dedup por conteúdo): o que muda é só o id do item STAC e a linha de `plat.raster_item`."""
    from app import db
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri
    from tests.api.imagens.apoio_raster import semear_raster

    base = semear_raster(tenant_id_a, "demo")
    item_id = f"zt-l102b-{secrets.token_hex(4)}"  # id de item STAC que NÃO é uuid
    ctx = db.Contexto(tenant_id=tenant_id_a, usuario_id=0, login="teste")
    with db.db(ctx) as cur:
        stac = ps.item_obter(cur, tenant_id_a, base["colecao"], base["item_id"])
        assert stac, "semear_raster não deixou o item no pgstac"
        novo = dict(stac)
        novo["id"] = item_id
        ps.item_criar(cur, tenant_id_a, base["colecao"], novo)
        ri.espelhar(cur, tenant_id_a, base["colecao"], item_id,
                    {"sha256": None, "perfil": "cientifico", "bytes": 0, "estado": "ativo"})
    yield {"item_id": item_id, "colecao": base["colecao"], "outro_item": base["item_id"]}
    with db.db(ctx) as cur:
        ps.item_apagar(cur, item_id, base["colecao"])


def test_token_com_escopo_de_item_stac_nao_uuid_e_criado(sessao_a, raster_nao_uuid):
    """A recusa por vocabulário caiu: o escopo por lista aceita id de item STAC."""
    r = sessao_a.post("/api/tokens", json={
        "nome": f"zt-l102b-{secrets.token_hex(4)}",
        "escopos": [f"tiles:ler:{raster_nao_uuid['item_id']}"]})
    assert r.status_code == 201, r.text
    sessao_a.delete(f"/api/tokens/{r.json()['id']}")


@pytest.fixture(scope="module")
def token_escopado(sessao_a, raster_nao_uuid):
    r = sessao_a.post("/api/tokens", json={
        "nome": f"zt-l102b-par-{secrets.token_hex(4)}",
        "escopos": [f"tiles:ler:{raster_nao_uuid['item_id']}"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def test_par_positivo_o_token_legitimo_serve_o_tile_do_item_escopado(token_escopado, raster_nao_uuid):
    """PAR POSITIVO (regra da casa: provar a recusa exige provar que o legítimo serve). Sem isto, o
    teste de recusa abaixo passaria mesmo com a rota quebrada para todos."""
    c, tok, item = _cliente(), token_escopado["token"], raster_nao_uuid["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/info.json")
    assert r.status_code == 200, f"o token com tiles:ler:<item> deveria ler o PRÓPRIO item: {r.text}"
    # o ladrilho é derivado dos bounds REAIS do item (nunca um z/x/y digitado: fora da extensão o
    # serviço devolve 204 e o teste passaria a medir "vazio", não "servido")
    from app.imagens import tiles as _tiles

    oeste, sul, leste, norte = r.json()["bounds"]
    alvo = _tiles.TMS.tile((oeste + leste) / 2, (sul + norte) / 2, 12)
    z, x, y = alvo.z, alvo.x, alvo.y
    rt = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png")
    assert rt.status_code == 200, f"tile do item escopado deveria sair: {rt.status_code} {rt.text[:200]}"
    assert rt.headers["content-type"] == "image/png", rt.headers.get("content-type")
    assert rt.content[:8] == b"\x89PNG\r\n\x1a\n", "o corpo não é um PNG"


def test_par_negativo_o_mesmo_token_nao_abre_outro_item(token_escopado, raster_nao_uuid):
    """Escopo por LISTA é lista: o token de um item não serve o item vizinho do MESMO inquilino."""
    c, tok = _cliente(), token_escopado["token"]
    r = c.get(f"/svc/{tok}/raster/{raster_nao_uuid['outro_item']}/info.json")
    assert r.status_code == 403, f"item fora da lista do escopo deveria dar 403; deu {r.status_code}"
    assert r.json()["erro"] == "escopo_insuficiente", r.text


def test_escopo_de_item_inexistente_continua_recusado(sessao_a):
    """A folga do vocabulário não pode virar folga de POSSE: id que não existe segue em 422."""
    r = sessao_a.post("/api/tokens", json={
        "nome": f"zt-l102b-fantasma-{secrets.token_hex(4)}",
        "escopos": [f"tiles:ler:zt-nao-existe-{secrets.token_hex(6)}"]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "escopo_item_inexistente", r.text


def test_escopo_de_item_de_outro_inquilino_e_recusado(sessao_a, tenant_id_b):
    """O item existe — no inquilino B. Para o dono de A tem de ser indistinguível de inexistente."""
    from app import db
    from app.imagens import pgstac as ps

    colecao = ps.nome_colecao(tenant_id_b, "imagens")
    item_id = f"zt-l102b-doB-{secrets.token_hex(4)}"
    ctx = db.Contexto(tenant_id=tenant_id_b, usuario_id=0, login="teste")
    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id_b, colecao) is None:
            ps.colecao_criar(cur, tenant_id_b, "imagens", {"title": "Imagens", "description": "x"})
        ps.item_criar(cur, tenant_id_b, colecao, item_stac(item_id, colecao))
    try:
        r = sessao_a.post("/api/tokens", json={
            "nome": f"zt-l102b-cruzado-{secrets.token_hex(4)}", "escopos": [f"tiles:ler:{item_id}"]})
        assert r.status_code == 422, f"item de OUTRO inquilino não pode ser escopado: {r.text}"
        assert r.json()["erro"] == "escopo_item_inexistente", r.text
    finally:
        with db.db(ctx) as cur:
            ps.item_apagar(cur, item_id, colecao)


def test_escopo_com_dois_pontos_no_id_continua_fora_do_vocabulario(sessao_a):
    """`:` é o separador do próprio escopo — deixá-lo entrar no id tornaria `tiles:ler:a:b` ambíguo."""
    from app.auth import escopos as esc

    assert not esc.valido("tiles:ler:item:com:dois-pontos")
    assert not esc.valido("tiles:ler:" + "x" * 200), "id acima de 128 caracteres tem de ser recusado"
    assert esc.valido("tiles:ler:item-nao-uuid-1")
    assert esc.valido("tiles:ler:S2B_MSIL2A_20260101T133229_R081_T23LLG_20260101T190000")
