"""API do tipo `estilo` (item L2-02-a-modelo-estilo): gravação recusa estilo inválido (422, com o campo
apontado), nunca silenciosamente na hora de desenhar; ida e volta sem perda; e a bateria da refutação
(campo inexistente, 300 layers, sprite de URL externa, inquilino cruzado)."""

import copy
import json

import pytest

from app.estilos import compilador

ITEM = "L2-02-a"


def _documento(pc: dict, maplibre: dict | None = None) -> dict:
    return {"esquema_versao": 1, "corpo": {"plat_construtor": pc, "maplibre": maplibre or compilador.compilar(pc)}}


PC_UNICO = {"tipo": "unico", "geometria": "poligono", "versao": 1, "simbolo": {"cor": "#4e79a7"}}
PC_CATEGORIA = {
    "tipo": "categoria", "geometria": "poligono", "versao": 1, "campo": "classe_uso",
    "campos": ["classe_uso"],
    "categorias": [{"valor": "lavoura", "cor": "#f28e2b"}, {"valor": "pastagem", "cor": "#e15759"}],
}
PC_CLASSES = {
    "tipo": "classes", "geometria": "poligono", "versao": 1, "campo": "area_ha", "campos": ["area_ha"],
    "classes": [{"min": 0, "max": 50, "cor": "#deebf7"}, {"min": 50, "max": 1000, "cor": "#08519c"}],
}
PC_RASTER = {
    "tipo": "raster", "geometria": "raster", "versao": 1,
    "parametros_raster": {
        "bandas": [4, 3, 2], "colormap_name": "viridis", "rescale": [0, 3000],
        "resampling": "bilinear", "nodata": 0,
        "esticamento": {"metodo": "minmax"},
    },
}


def criar_estilo(sessao, itens, pc, maplibre=None, **extra):
    corpo = {"tipo": "estilo", "titulo": "zt estilo teste", "dados": _documento(pc, maplibre)}
    corpo.update(extra)
    r = sessao.post("/api/itens", json=corpo)
    if r.status_code == 201:
        itens.criados.append(r.json()["id"])
    return r


# ---------------------------------------------------------------- esquema publicado
def test_esquema_do_tipo_estilo_e_o_arquivo_publicado(sessao_a):
    from pathlib import Path

    r = sessao_a.get("/api/esquemas/estilo")
    assert r.status_code == 200
    do_banco = r.json()
    arquivo = Path(__file__).resolve().parents[3] / "docs" / "esquemas" / "estilo-v1.json"
    esperado = json.loads(arquivo.read_text(encoding="utf-8"))
    # numa trilha isolada (item L7-31), CursorSchemaAmbiente reescreve toda ocorrência textual de "plat"
    # para o schema da trilha (ex.: plat_testilo) — inclusive dentro de uma string humana como o `title`
    # deste esquema, que não é referência de schema nenhuma. Mesmo achado em `mapa-v1.json` (item
    # L2-01-a-documento-mapa): não é bug deste item, é o rewriter sendo largo demais; comparação
    # normaliza o título para não depender do nome da trilha em que o teste roda.
    do_banco["title"] = esperado["title"] = "documento de estilo do plat (estilo-v1)"
    assert esperado == do_banco
    tipos = do_banco["properties"]["corpo"]["properties"]["plat_construtor"]["properties"]["tipo"]["enum"]
    assert set(tipos) == {"unico", "categoria", "classes", "proporcional", "calor", "agrupamento", "raster"}


# ---------------------------------------------------------------- ciclo de vida + ida e volta
@pytest.mark.parametrize("pc", [PC_UNICO, PC_CATEGORIA, PC_CLASSES])
def test_criar_ler_e_o_documento_lido_e_igual_ao_gravado(sessao_a, itens_a, pc):
    r = criar_estilo(sessao_a, itens_a, pc)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    lido = sessao_a.get(f"/api/itens/{eid}")
    assert lido.status_code == 200
    assert lido.json()["dados"]["corpo"]["plat_construtor"] == pc
    assert lido.json()["dados"]["corpo"]["maplibre"] == compilador.compilar(pc)


def test_raster_salvo_e_reaberto_e_identico(sessao_a, itens_a):
    """cláusula do portão do item L2-02-f: `plat_construtor.parametros_raster` (bandas, colormap,
    rescale, resampling, nodata, esticamento) sobrevive intacto ao ciclo gravar/ler, e o `maplibre`
    lido é exatamente o que `compilador.compilar` calcula do MESMO documento — nunca dois estados."""
    r = criar_estilo(sessao_a, itens_a, PC_RASTER)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    lido = sessao_a.get(f"/api/itens/{eid}")
    assert lido.status_code == 200
    assert lido.json()["dados"]["corpo"]["plat_construtor"] == PC_RASTER
    assert lido.json()["dados"]["corpo"]["maplibre"] == compilador.compilar(PC_RASTER)

    # segunda volta: gravar de novo o que foi lido dá byte a byte o mesmo (ida-e-volta sem perda)
    r2 = sessao_a.post("/api/itens", json={
        "tipo": "estilo", "titulo": "zt estilo raster reimportado", "dados": lido.json()["dados"],
    })
    assert r2.status_code == 201, r2.text
    itens_a.criados.append(r2.json()["id"])
    lido2 = sessao_a.get(f"/api/itens/{r2.json()['id']}")
    assert lido2.json()["dados"] == lido.json()["dados"]


def test_exportar_e_importar_devolve_documento_igual_exceto_id(sessao_a, itens_a):
    """Ida e volta sem perda: o documento de um estilo gravado, exportado (GET) e importado de novo
    (POST com o mesmo `dados`) produz outro item cujo `dados` bate byte a byte com o original."""
    r1 = criar_estilo(sessao_a, itens_a, PC_CLASSES)
    assert r1.status_code == 201, r1.text
    exportado = sessao_a.get(f"/api/itens/{r1.json()['id']}").json()["dados"]

    r2 = sessao_a.post(
        "/api/itens", json={"tipo": "estilo", "titulo": "zt estilo reimportado", "dados": exportado}
    )
    assert r2.status_code == 201, r2.text
    itens_a.criados.append(r2.json()["id"])
    reimportado = sessao_a.get(f"/api/itens/{r2.json()['id']}").json()["dados"]
    assert reimportado == exportado  # diff vazio na parte que importa (id do item não faz parte de `dados`)


def test_maplibre_enviado_e_sempre_substituido_pelo_canonico(sessao_a, itens_a):
    """O que fica gravado é sempre `compilar(plat_construtor)`, nunca o `maplibre` literal que o cliente
    mandou (ver docstring de app/estilos/validador.py) — mesmo um `maplibre` válido, mas diferente do
    canônico, some na gravação."""
    maplibre_diferente = {"version": 8, "layers": [{"id": "outro-nome", "type": "fill",
                                                     "paint": {"fill-color": "#000000", "fill-opacity": 0.2}}]}
    r = criar_estilo(sessao_a, itens_a, PC_UNICO, maplibre=maplibre_diferente)
    assert r.status_code == 201, r.text
    lido = sessao_a.get(f"/api/itens/{r.json()['id']}").json()
    assert lido["dados"]["corpo"]["maplibre"] == compilador.compilar(PC_UNICO)
    assert lido["dados"]["corpo"]["maplibre"] != maplibre_diferente


# ---------------------------------------------------------------- refutação: recusado na gravação
def test_estilo_invalido_contra_a_style_spec_e_422_com_a_mensagem_do_validador(sessao_a, itens_a):
    maplibre_ruim = {"version": 8, "layers": [{"id": "camada", "type": "fill",
                                                "paint": {"fill-color-BOGUS": "#000000"}}]}
    r = criar_estilo(sessao_a, itens_a, PC_UNICO, maplibre=maplibre_ruim)
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "estilo_invalido"
    assert "fill-color-BOGUS" in json.dumps(j)  # a mensagem do validador oficial, repassada ao cliente


def test_campo_fora_do_vocabulario_na_expressao_e_422(sessao_a, itens_a):
    maplibre_com_campo_estranho = copy.deepcopy(compilador.compilar(PC_CATEGORIA))
    maplibre_com_campo_estranho["layers"][0]["paint"]["fill-color"] = [
        "case", ["==", ["get", "campo_fantasma"], "x"], "#000000", "#ffffff",
    ]
    r = criar_estilo(sessao_a, itens_a, PC_CATEGORIA, maplibre=maplibre_com_campo_estranho)
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "campo_inexistente"
    assert j["detalhe"]["campo"] == "campo_fantasma"


def test_faixa_de_classe_invertida_e_422(sessao_a, itens_a):
    pc = copy.deepcopy(PC_CLASSES)
    pc["classes"][0]["min"], pc["classes"][0]["max"] = 999, 1
    r = criar_estilo(sessao_a, itens_a, pc, maplibre={"version": 8, "layers": [{"id": "camada", "type": "fill",
                                                                                 "paint": {"fill-color": "#000000"}}]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "plat_construtor_invalido"


def test_300_layers_e_recusado_pelo_esquema(sessao_a, itens_a):
    layers = [{"id": f"l{i}", "type": "fill", "paint": {"fill-color": "#000000"}} for i in range(300)]
    r = criar_estilo(sessao_a, itens_a, PC_UNICO, maplibre={"version": 8, "layers": layers})
    assert r.status_code == 422, r.text
    j = r.json()
    assert j["erro"] == "dados_invalidos"
    assert any("maplibre.layers" in d["campo"] for d in j["detalhe"])


def test_sprite_de_url_externa_e_recusado(sessao_a, itens_a):
    r = criar_estilo(
        sessao_a, itens_a, PC_UNICO,
        maplibre={**compilador.compilar(PC_UNICO), "sprite": "https://cdn.externo.com/sprites/malicioso"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "dados_invalidos"


def test_categoria_com_valores_duplicados_e_422(sessao_a, itens_a):
    pc = copy.deepcopy(PC_CATEGORIA)
    pc["categorias"].append({"valor": "lavoura", "cor": "#111111"})
    r = criar_estilo(sessao_a, itens_a, pc, maplibre=compilador.compilar(PC_CATEGORIA))
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "plat_construtor_invalido"


# ---------------------------------------------------------------- refutação: inquilino cruzado
def test_estilo_de_um_inquilino_nao_e_legivel_por_outro(sessao_a, sessao_b, itens_a):
    r = criar_estilo(sessao_a, itens_a, PC_UNICO)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    cruzado = sessao_b.get(f"/api/itens/{eid}")
    assert cruzado.status_code == 404
