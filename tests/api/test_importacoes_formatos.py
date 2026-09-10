"""`GET /api/importacoes/formatos` (item L0-04) tem de vir ANTES de `/api/importacoes/{id}` no router: com a ordem
invertida a rota devolvia 404 importacao_inexistente (achado do item UX-16-ingestao-sem-tela)."""


def test_formatos_aceitos_responde_a_lista_e_nao_404(sessao_a):
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, r.text
    tipos = {f["tipo"] for f in r.json()}
    assert {"geojson", "csv", "gpkg", "shapefile.zip"} <= tipos, tipos
    assert all(f["extensoes"] and f["rotulo"] for f in r.json())
