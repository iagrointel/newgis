"""Portão do item L1-02-i-ogc-api-tiles-e-maps, cláusula "landing page e conformance declaram as
classes implementadas e passam no validador OGC (ETS de Tiles) quando disponível, ou em teste próprio
contra o JSON Schema da spec".

Não existe um ETS (executable test suite) oficial de OGC API — Tiles publicado para rodar offline
nesta bancada (o Compliance Test Suite do OGC roda contra um endpoint público hospedado pela Teamengine
— fora do escopo de uma suíte que não depende de rede em CI). A alternativa que o próprio portão prevê
é esta: os JSON Schema da especificação (recorte de `ogcapi-tiles-1.bundled.json`, o documento OpenAPI
BUNDLED — todos os `$ref` já resolvidos — da OGC API — Tiles Part 1, baixado em 10/09/2026; ver
`tests/dados/ogc_schemas/README.md`) validando a resposta REAL da aplicação, não uma cópia escrita à
mão do formato esperado.

Achado do adversário independente (turno 9): a suíte anterior deste item media campo a campo
(`corpo["dataType"] == "map"` etc.) mas nunca validava contra o esquema oficial — o portão pede
explicitamente um dos dois (ETS ou JSON Schema), e só o primeiro existia (parcialmente, indireto).
Este arquivo fecha a lacuna."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ESQUEMAS = json.loads((ROOT / "tests" / "dados" / "ogc_schemas" / "ogcapi-tiles-1.bundled.json")
                      .read_text(encoding="utf-8"))
Z, X, Y = 12, 1503, 2230


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def token_ogc(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-ogc-schema", "escopos": ["tiles:ler", "imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def _validar(instancia: dict, nome_schema: str) -> None:
    """`instancia` contra `components.schemas.<nome_schema>` do documento bundled — `$ref` internos
    (`#/components/schemas/...`) resolvidos contra o MESMO documento (`RefResolver.from_schema`, a
    técnica clássica para um schema com refs internos; o `jsonschema` 4.x marca isso como legado mas
    ainda funciona — não há substituto de uma linha só na API nova para "resolver contra o próprio
    documento", e trocar de biblioteca não cabe no escopo deste item)."""
    import jsonschema

    schema = {"$ref": f"#/components/schemas/{nome_schema}"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resolver = jsonschema.RefResolver.from_schema(ESQUEMAS)
        validador = jsonschema.Draft7Validator(schema, resolver=resolver)
        erros = sorted(validador.iter_errors(instancia), key=lambda e: list(e.path))
    if erros:
        detalhe = "\n".join(f"  - {'/'.join(str(p) for p in e.path) or '(raiz)'}: {e.message}" for e in erros)
        pytest.fail(f"{nome_schema}: {len(erros)} violação(ões) do esquema oficial:\n{detalhe}")


def test_landing_valida_no_schema_landingpage_da_spec(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles")
    assert r.status_code == 200, r.text
    _validar(r.json(), "landingPage")


def test_conformance_valida_no_schema_confclasses_da_spec(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/conformance")
    assert r.status_code == 200, r.text
    _validar(r.json(), "confClasses")


def test_tile_matrix_sets_lista_valida_no_schema_tilematrixset_item(token_ogc):
    """A lista (`/tileMatrixSets`) não tem um nome de componente próprio no documento bundled — o
    schema mora inline em `components.responses.TileMatrixSetsList` — então este teste valida CADA
    elemento do array contra `tileMatrixSet-item` (o componente que esse response referencia)."""
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/tileMatrixSets")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert isinstance(corpo.get("tileMatrixSets"), list) and corpo["tileMatrixSets"]
    for item in corpo["tileMatrixSets"]:
        _validar(item, "tileMatrixSet-item")


def test_tile_matrix_set_definicao_valida_no_schema_tilematrixset_da_spec(token_ogc):
    c, tok = _cliente(), token_ogc["token"]
    r = c.get(f"/svc/{tok}/ogc/tiles/tileMatrixSets/WebMercatorQuad")
    assert r.status_code == 200, r.text
    _validar(r.json(), "tileMatrixSet")


def test_tileset_metadata_valida_no_schema_tileset_da_spec(token_ogc, raster_demo):
    c, tok, item = _cliente(), token_ogc["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/ogc/tiles/collections/{item}/map/tiles/WebMercatorQuad")
    assert r.status_code == 200, r.text
    _validar(r.json(), "tileSet")
