"""Rotas /api/analise3d (item L2-09-d-analise-3d-visibilidade).

O que a suíte de API prova além da unidade: as quatro rotas sob SESSÃO e sob TOKEN com o escopo
`analise3d:usar`; `salvar_item` cria item `analise_3d` do catálogo (com os quatro blocos exigidos
pelo JSON Schema do tipo) e o observador SEM `conteudo.criar` recebe 403; a RLS separa o item de A
do inquilino B; e os erros de entrada viram 422 com o código do motivo.
"""

import math
import secrets

from tests.api.conftest import novo_cliente

SRID = 31983
X0, Y0 = 220000.0, 7450000.0
CELULA = 20.0


def terreno_sintetico() -> dict:
    """4x4 células de 20 m; morro de 60 m no centro (célula entre as 4 centrais)."""
    alturas = []
    for i in range(4):
        linha = []
        for j in range(4):
            r2 = (j * CELULA - 30.0) ** 2 + (i * CELULA - 30.0) ** 2
            linha.append(round(60.0 * math.exp(-r2 / (2 * 20.0**2)), 3))
        alturas.append(linha)
    return {"srid": SRID, "x0": X0, "y0": Y0, "celula_m": CELULA, "alturas": alturas}


def corpo_visada(salvar=None) -> dict:
    corpo = {
        "terreno": terreno_sintetico(),
        "observador": [X0 + CELULA, Y0 + 2 * CELULA],
        "alvo": [X0 + 3 * CELULA, Y0 + 2 * CELULA],
        "altura_observador_m": 2.0,
    }
    if salvar is not None:
        corpo["salvar_item"] = {"titulo": salvar}
    return corpo


def test_visada_sob_sessao_salva_item_do_catalogo(sessao_a):
    r = sessao_a.post("/api/analise3d/visada", json=corpo_visada(f"zt-analise3d-visada-{secrets.token_hex(3)}"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["visivel"] is False and d["ponto_de_obstrucao"] is not None
    assert d["procedencia"]["analise"] == "visada" and len(d["procedencia"]["sha256_terreno"]) == 64
    item = sessao_a.get(f"/api/itens/{d['item_id']}").json()
    assert item["tipo"] == "analise_3d"
    assert set(item["dados"].keys()) >= {"analise", "parametros", "resultado", "procedencia"}
    assert item["dados"]["analise"] == "visada"


def test_viewshed_sob_sessao_item_guarda_resumo(sessao_a):
    r = sessao_a.post("/api/analise3d/viewshed", json={
        "terreno": terreno_sintetico(),
        "observador": [X0 + 2 * CELULA, Y0 + 2 * CELULA],
        "altura_observador_m": 5.0,
        "distancia_max_m": 20000.0,
        "salvar_item": {"titulo": f"zt-analise3d-viewshed-{secrets.token_hex(3)}"},
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ferramenta"] == "gdal_viewshed" and "GDAL" in d["versao_gdal"]
    assert d["celulas_visiveis"] > 0 and d["png_viewshed_base64"]
    item = sessao_a.get(f"/api/itens/{d['item_id']}").json()
    assert item["dados"]["resultado"]["resumido_no_item"] is True
    assert "geotiff_base64" not in item["dados"]["resultado"]
    assert item["dados"]["resultado"]["sha256_viewshed_geotiff"] == d["sha256_viewshed_geotiff"]


def test_perfil_sob_sessao(sessao_a):
    r = sessao_a.post("/api/analise3d/perfil", json={
        "terreno": terreno_sintetico(),
        "ponto_a": [X0, Y0 + 2 * CELULA],
        "ponto_b": [X0 + 4 * CELULA, Y0 + 2 * CELULA],
        "n_amostras": 20,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["amostras"]) == 20 and d["estatisticas"]["z_max_m"] > d["estatisticas"]["z_min_m"]
    assert d["procedencia"]["analise"] == "perfil"


def test_sombra_sob_sessao_meio_dia_de_dezembro(sessao_a):
    # 12:06 do fuso -03:00 é o meio-dia solar de 21/12 nessa longitude (lon ≈ −46,6°); a unidade
    # (test_analise3d_sombra) prova a fórmula fechada no instante exato — aqui a rota inteira
    r = sessao_a.post("/api/analise3d/sombra", json={
        "srid": SRID,
        "data_hora": "2026-12-21T12:06:00-03:00",
        "solidos": [{"poligono": {"type": "Polygon", "coordinates": [[
            [X0, Y0], [X0 + 10, Y0], [X0 + 10, Y0 + 10], [X0, Y0 + 10], [X0, Y0],
        ]]}, "altura_m": 20.0}],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    so = d["solidos"][0]
    assert so["elevacao_sol_graus"] > 87.0 and so["comprimento_sombra_m"] < 2.0
    assert so["sombra_geojson"]["type"] == "Polygon"


def test_sombra_sem_conteudo_criar_e_403_ao_salvar(sessao_a, usuarios_a):
    c, _u, _s = usuarios_a.sessao(perfil="visualizador")
    corpo = corpo_visada("deveria ser proibido")
    r = c.post("/api/analise3d/visada", json=corpo)
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio", r.text
    # sem salvar_item o visualizador calcula (leitura do próprio inquilino)
    del corpo["salvar_item"]
    r2 = c.post("/api/analise3d/visada", json=corpo)
    assert r2.status_code == 200 and "item_id" not in r2.json()


def test_sombra_sol_abaixo_do_horizonte_e_data_sem_fuso_sao_422(sessao_a):
    base = {"srid": SRID, "solidos": [{"poligono": {"type": "Polygon", "coordinates": [[
        [X0, Y0], [X0 + 10, Y0], [X0 + 10, Y0 + 10], [X0, Y0 + 10], [X0, Y0]]]}, "altura_m": 10.0}]}
    r = sessao_a.post("/api/analise3d/sombra", json={**base, "data_hora": "2026-12-21T22:00:00-03:00"})
    assert r.status_code == 422 and r.json()["erro"] == "sol_abaixo_do_horizonte", r.text
    r2 = sessao_a.post("/api/analise3d/sombra", json={**base, "data_hora": "2026-12-21T12:00:00"})
    assert r2.status_code == 422 and r2.json()["erro"] == "data_sem_fuso", r2.text


def test_srid_fora_da_faixa_e_422(sessao_a):
    corpo = corpo_visada()
    corpo["terreno"]["srid"] = 4326  # graus, não metro: a análise 3D recusa
    r = sessao_a.post("/api/analise3d/visada", json=corpo)
    assert r.status_code == 422 and r.json()["erro"] == "srid_invalido", r.text


def test_item_de_analise_e_invisivel_para_outro_inquilino(sessao_a, sessao_b):
    r = sessao_a.post("/api/analise3d/perfil", json={
        "terreno": terreno_sintetico(),
        "ponto_a": [X0, Y0], "ponto_b": [X0 + 4 * CELULA, Y0 + 4 * CELULA],
        "n_amostras": 5,
        "salvar_item": {"titulo": f"zt-analise3d-perfil-{secrets.token_hex(3)}"},
    })
    assert r.status_code == 200, r.text
    iid = r.json()["item_id"]
    assert sessao_b.get(f"/api/itens/{iid}").status_code == 404


def test_token_com_escopo_analise3d_usa_as_rotas(sessao_a):
    nome = f"zt-analise3d-token-{secrets.token_hex(3)}"
    r = sessao_a.post("/api/tokens", json={"nome": nome, "escopos": ["analise3d:usar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    cab = {"Authorization": f"Bearer {tok['token']}"}
    por_token = novo_cliente()  # sem cookie: sessão + Bearer juntos são recusados (autenticação ambígua)
    try:
        r2 = por_token.post("/api/analise3d/perfil", json={
            "terreno": terreno_sintetico(),
            "ponto_a": [X0, Y0], "ponto_b": [X0 + 4 * CELULA, Y0], "n_amostras": 4,
        }, headers=cab)
        assert r2.status_code == 200, r2.text
        # o privilégio vem do DONO do token (plat.privilegios_de): o dono admin tem conteudo.criar,
        # então o token com salvar_item cria o item — e o teste apaga o que criou
        r3 = por_token.post(
            "/api/analise3d/visada",
            json=corpo_visada(f"zt-analise3d-tokitem-{secrets.token_hex(3)}"), headers=cab,
        )
        assert r3.status_code == 200 and r3.json()["item_id"], r3.text
        assert sessao_a.delete(f"/api/itens/{r3.json()['item_id']}").status_code in (200, 204)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_token_sem_escopo_e_403(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"zt-analise3d-sem-escopo-{secrets.token_hex(3)}",
                                           "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    cab = {"Authorization": f"Bearer {tok['token']}"}
    por_token = novo_cliente()
    try:
        r2 = por_token.post("/api/analise3d/perfil", json={
            "terreno": terreno_sintetico(),
            "ponto_a": [X0, Y0], "ponto_b": [X0 + 4 * CELULA, Y0], "n_amostras": 4,
        }, headers=cab)
        assert r2.status_code == 403 and r2.json()["erro"] == "escopo_insuficiente", r2.text
        assert r2.json()["detalhe"]["exigido"] == "analise3d:usar"
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")
