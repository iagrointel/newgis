"""Compilador `plat_construtor` -> MapLibre (item L2-02-a-modelo-estilo): os 7 tipos do construtor
compilam, a mesma lista `classes()` alimenta o estilo e a legenda, e as falhas de construção viram
`EstiloInvalido` com o caminho do campo (a rota transforma isso em 422)."""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from app.estilos import compilador, padrao, sld

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "estilos"
TIPOS = ("unico", "categoria", "classes", "proporcional", "calor", "agrupamento", "raster")


def _carregar(nome: str) -> dict:
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("nome", TIPOS)
def test_fixture_de_cada_tipo_compila_de_novo_igual_ao_arquivo(nome):
    """Ida e volta sem perda: recompilar o `plat_construtor` do arquivo dá byte a byte o mesmo `maplibre`
    já gravado nele — a prova de que não existe segunda fonte de verdade."""
    doc = _carregar(nome)
    recompilado = compilador.compilar(doc["corpo"]["plat_construtor"])
    assert recompilado == doc["corpo"]["maplibre"]


@pytest.mark.parametrize("nome", TIPOS)
def test_fixture_de_cada_tipo_passa_no_validador_oficial(nome):
    doc = _carregar(nome)
    from app.estilos.validador import _FONTE_FICTICIA, VALIDADOR_JS, _layers_com_fonte

    completo = {
        "version": 8,
        "sources": _FONTE_FICTICIA,
        "layers": _layers_com_fonte(doc["corpo"]["maplibre"]["layers"]),
    }
    r = subprocess.run(
        ["node", str(VALIDADOR_JS)], input=json.dumps(completo), capture_output=True, text=True,
        cwd=str(VALIDADOR_JS.parent), timeout=10,
    )
    assert r.returncode == 0, r.stderr
    resultado = json.loads(r.stdout)
    assert resultado["ok"], resultado["erros"]


def test_legenda_e_o_estilo_saem_da_mesma_lista_de_classes():
    pc = _carregar("classes")["corpo"]["plat_construtor"]
    cls = compilador.classes(pc)
    leg = compilador.legenda(pc)
    ml = compilador.compilar(pc)
    # a expressão "case" do paint usa exatamente as cores de `classes()`, na mesma ordem
    cor_expr = ml["layers"][0]["paint"]["fill-color"]
    cores_no_case = cor_expr[2::2] + [cor_expr[-1]]
    assert cores_no_case == [c["cor"] for c in cls]
    assert [e["cor"] for e in leg] == [c["cor"] for c in cls]


def test_faixa_invertida_e_recusada():
    pc = copy.deepcopy(_carregar("classes")["corpo"]["plat_construtor"])
    pc["classes"][0]["min"], pc["classes"][0]["max"] = 999, 1
    with pytest.raises(compilador.EstiloInvalido, match="invertida"):
        compilador.compilar(pc)


def test_categoria_sem_campo_e_recusada():
    pc = {"tipo": "categoria", "geometria": "poligono", "versao": 1, "categorias": [{"valor": "a", "cor": "#000000"}]}
    with pytest.raises(compilador.EstiloInvalido, match="campo"):
        compilador.compilar(pc)


def test_categoria_com_valor_duplicado_e_recusada():
    pc = {
        "tipo": "categoria", "geometria": "poligono", "versao": 1, "campo": "x",
        "categorias": [{"valor": "a", "cor": "#000000"}, {"valor": "a", "cor": "#ffffff"}],
    }
    with pytest.raises(compilador.EstiloInvalido, match="duplicado"):
        compilador.compilar(pc)


def test_tipo_calor_fora_de_ponto_e_recusado():
    pc = {"tipo": "calor", "geometria": "poligono", "versao": 1, "calor": {"intensidade": 1, "raio_px": 10}}
    with pytest.raises(compilador.EstiloInvalido, match="ponto"):
        compilador.compilar(pc)


def test_tipo_desconhecido_e_recusado():
    with pytest.raises(compilador.EstiloInvalido, match="desconhecido"):
        compilador.compilar({"tipo": "inexistente", "geometria": "ponto", "versao": 1})


# ---------------------------------------------------------------- estilo padrão da ingestão
def test_estilo_padrao_e_deterministico_pelo_uuid():
    u = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    a = padrao.estilo_padrao(u, "poligono")
    b = padrao.estilo_padrao(u, "poligono")
    assert a == b
    assert padrao.cor_determinista(u) == padrao.cor_determinista(u)


def test_estilo_padrao_de_uuids_diferentes_pode_diferir_mas_e_estavel():
    cores = {padrao.cor_determinista(f"00000000-0000-0000-0000-{i:012d}") for i in range(30)}
    assert len(cores) > 1  # não é sempre a mesma cor
    assert all(c.startswith("#") and len(c) == 7 for c in cores)


# ---------------------------------------------------------------- SLD (unico/categoria/classes)
@pytest.mark.parametrize("nome", ["unico", "categoria", "classes"])
def test_sld_gerado_tem_as_mesmas_cores_do_construtor_lendo_o_xml(nome):
    import xml.etree.ElementTree as ET

    pc = _carregar(nome)["corpo"]["plat_construtor"]
    xml_txt = sld.gerar_sld(pc, "zt_camada")
    root = ET.fromstring(xml_txt)  # levanta se o XML for malformado
    cores_fill = [
        e.text for e in root.iter("{http://www.opengis.net/sld}CssParameter") if e.get("name") == "fill"
    ]
    esperado = [c["cor"] for c in compilador.classes(pc) if c["cor"]]
    assert cores_fill == esperado


def test_sld_nao_suportado_para_proporcional_calor_agrupamento_raster():
    for nome in ("proporcional", "calor", "agrupamento", "raster"):
        pc = _carregar(nome)["corpo"]["plat_construtor"]
        assert not sld.sld_suportado(pc)
        with pytest.raises(sld.SldNaoSuportado):
            sld.gerar_sld(pc)
