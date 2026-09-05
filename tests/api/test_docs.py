"""/api/docs: Swagger UI com todos os recursos locais (sem CDN, sem validador externo); /redoc e /docs não existem."""

import re

EXTERNO = re.compile(r"https?://")


def test_api_docs_nao_referencia_dominio_externo(cliente):
    r = cliente.get("/api/docs")
    assert r.status_code == 200
    html = r.text
    assert "swagger-ui-bundle-5.32.15.js" in html and "swagger-ui-5.32.15.css" in html
    referencias = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert referencias and all(ref.startswith("/") for ref in referencias), referencias
    assert not EXTERNO.search(html), EXTERNO.findall(html)
    assert '"validatorUrl": null' in html


def test_openapi_local_e_docs_antigos_ausentes(cliente):
    assert cliente.get("/api/openapi.json").status_code == 200
    for rota in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(rota).status_code == 404, rota
