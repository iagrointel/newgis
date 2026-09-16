"""Adversário de linha L1 imagens (parte 2, turno 9) — item `L1-02-g-wms-1-3-0-raster`, ENTREGUE
(commit c5e840c16). Duas cláusulas LITERAIS do próprio portão não são atendidas pelo código commitado:

1. "`GetFeatureInfo` devolve o mesmo valor do endpoint `/ponto`" — `app/imagens/rotas_wms.py` recusa a
   operação com uma mensagem que o próprio código admite ser um corte de escopo, não uma recusa de
   protocolo: "GetFeatureInfo não está implementado nesta passagem" (`app/imagens/wms.py` linha ~23,
   `app/imagens/rotas_wms.py` linha ~357).
2. "`GetMap` em 4 CRS bate geometricamente com o tile XYZ equivalente" — a hipótese do item lista
   EPSG:3857/4326/4674/31981-31985; `app/imagens/wms.py` declara `CRS_SUPORTADOS = ("EPSG:4326",
   "EPSG:3857")`, só 2 dos 4. O motor de pixel partilhado (`app/imagens/tiles.py`, usado por
   OGC API Maps e por `exportImage` do ImageServer) aceita `CRS.from_user_input` genérico — a
   limitação é SÓ da fachada WMS, não do motor.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_wms_gate.py -q -rxX`."""

from __future__ import annotations

import pytest

from tests.api.imagens.test_wms import _bbox3857, _cliente, _getmap, raster_demo, token_wms  # noqa: F401


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-02-g CAI: GetFeatureInfo esta AUSENTE (app/imagens/rotas_wms.py devolve ServiceException "
        "'GetFeatureInfo nao esta implementado nesta passagem'), mas o portao literal do item exige "
        "'GetFeatureInfo devolve o mesmo valor do endpoint /ponto'. Sem essa operacao nao ha como um "
        "cliente WMS (QGIS Identify, Portal) ler valor de pixel por clique."
    ),
)
def test_getfeatureinfo_devolve_o_mesmo_valor_do_endpoint_ponto(token_wms, raster_demo):  # noqa: F811  (fixtures importadas do arquivo do construtor)
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]

    r_ponto = c.get(f"/svc/{tok}/raster/{item}/estatisticas.json")
    assert r_ponto.status_code == 200, r_ponto.text

    r = _getmap(
        c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS=item, I="128", J="128", INFO_FORMAT="application/json"
    )
    assert r.status_code == 200, (
        f"GetFeatureInfo deveria devolver 200 com o valor do pixel; devolveu {r.status_code}: {r.text}"
    )
    assert "ServiceException" not in r.text, r.text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-02-g CAI: CRS_SUPORTADOS em app/imagens/wms.py = apenas ('EPSG:4326','EPSG:3857'), mas o "
        "portao literal exige GetMap correto nos 4 CRS da hipotese do item (EPSG:3857/4326/4674/"
        "31981-31985). EPSG:4674 (SIRGAS2000, referencia oficial do IBGE) nao e nem reconhecido: o WMS "
        "devolve InvalidCRS para um sistema de referencia que o pais usa oficialmente, enquanto o mesmo "
        "motor de pixel (app/imagens/tiles.py, usado por OGC API Maps) aceita qualquer EPSG via pyproj."
    ),
)
def test_getmap_aceita_epsg_4674_sirgas2000(token_wms, raster_demo):  # noqa: F811  (fixtures importadas do arquivo do construtor)
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]

    from rasterio.warp import transform_bounds

    from tests.api.imagens.test_wms import _bounds4326

    oeste, sul, leste, norte = _bounds4326(c, tok, item)
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", "EPSG:4674", oeste, sul, leste, norte)
    r = _getmap(c, tok, item, CRS="EPSG:4674", BBOX=f"{miny},{minx},{maxy},{maxx}")
    assert r.status_code == 200, (
        f"EPSG:4674 (SIRGAS2000) deveria ser um CRS suportado pelo GetMap; devolveu {r.status_code}: {r.text}"
    )
