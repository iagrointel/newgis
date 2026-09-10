"""Unidade do bloco `plat_construtor.rotulos` -> layers `symbol` (item L2-02-d-rotulos,
`app/estilos/compilador.py::_rotulos_layers`). Separado de tests/unit/test_estilos_compilador.py
(arquivo compartilhado com L2-02-a/L2-02-f) para não colidir na fila de junção."""

import json
import subprocess
from pathlib import Path

import pytest

from app.estilos import compilador
from app.estilos.compilador import EstiloInvalido
from app.estilos.rotulos_servidor import nome_coluna_servidor

RAIZ = Path(__file__).resolve().parents[2]
VALIDADOR_JS = RAIZ / "ferramentas" / "estilo" / "validar.mjs"


def _pc_ponto(rotulos):
    return {
        "tipo": "unico",
        "geometria": "ponto",
        "campo": None,
        "campos": ["area_ha", "classe_uso"],
        "simbolo": {"cor": "#336699"},
        "rotulos": rotulos,
    }


def _valida_style_spec(doc_completo):
    doc = {
        "version": 8,
        "sources": {"camada": {"type": "vector", "tiles": ["https://x.invalido/{z}/{x}/{y}"]}},
        "layers": [{**la, "source": "camada", "source-layer": "camada"} for la in doc_completo["layers"]],
    }
    if doc_completo.get("glyphs"):
        doc["glyphs"] = doc_completo["glyphs"]
    r = subprocess.run(
        ["node", str(VALIDADOR_JS)],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        cwd=str(VALIDADOR_JS.parent),
        timeout=10,
    )
    assert r.returncode == 0, r.stderr
    resultado = json.loads(r.stdout)
    assert resultado["ok"], resultado.get("erros")


class TestRotuloPorCampo:
    def test_layer_symbol_com_get_do_campo(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "area_ha"}, "cor": "#111111"}]})
        doc = compilador.compilar(pc)
        rotulo = [la for la in doc["layers"] if la["type"] == "symbol"]
        assert len(rotulo) == 1
        assert rotulo[0]["layout"]["text-field"] == ["get", "area_ha"]
        assert rotulo[0]["paint"]["text-color"] == "#111111"
        _valida_style_spec(doc)

    def test_campo_fora_do_vocabulario_e_recusado(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "fora_da_lista"}}]})
        with pytest.raises(EstiloInvalido):
            compilador.compilar(pc)

    def test_unidade_concatena_sufixo(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "area_ha"}, "unidade": "ha"}]})
        doc = compilador.compilar(pc)
        campo = doc["layers"][-1]["layout"]["text-field"]
        assert campo == ["concat", ["to-string", ["get", "area_ha"]], " ", "ha"]

    def test_maiusculas_vira_text_transform(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "maiusculas": True}]})
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["layout"]["text-transform"] == "uppercase"


class TestRotuloPorExpressao:
    def test_expressao_compilavel_vira_expressao_maplibre(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"expressao": "Concatenar('a: ', $classe_uso)"}}]})
        doc = compilador.compilar(pc)
        campo = doc["layers"][-1]["layout"]["text-field"]
        assert campo[0] == "concat"
        assert doc["layers"][-1]["metadata"].get("plat:rotulo_servidor") is not True

    def test_expressao_nao_compilavel_cai_para_coluna_do_servidor(self):
        expressao = "TextoNumero($area_ha, 1)"
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"expressao": expressao}, "unidade": "ha"}]})
        doc = compilador.compilar(pc)
        layer = doc["layers"][-1]
        assert layer["metadata"]["plat:rotulo_servidor"] is True
        assert layer["metadata"]["plat:rotulo_coluna_servidor"] == ["get", nome_coluna_servidor(expressao)]
        assert layer["layout"]["text-field"] == [
            "concat",
            ["to-string", ["get", nome_coluna_servidor(expressao)]],
            " ",
            "ha",
        ]
        _valida_style_spec(doc)

    def test_texto_exige_campo_ou_expressao(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {}}]})
        with pytest.raises(EstiloInvalido):
            compilador.compilar(pc)


class TestClassesComFiltroEPrioridade:
    def test_duas_classes_com_filtro_viram_dois_layers_com_filter(self):
        pc = _pc_ponto(
            {
                "visivel": True,
                "classes": [
                    {
                        "nome": "A",
                        "texto": {"campo": "classe_uso"},
                        "filtro": {"campo": "classe_uso", "operador": "==", "valor": "lavoura"},
                        "prioridade": 1,
                    },
                    {
                        "nome": "B",
                        "texto": {"campo": "classe_uso"},
                        "filtro": {"campo": "classe_uso", "operador": "==", "valor": "pastagem"},
                        "prioridade": 2,
                    },
                ],
            }
        )
        doc = compilador.compilar(pc)
        rotulos = [la for la in doc["layers"] if la["type"] == "symbol"]
        assert len(rotulos) == 2
        # ORDEM decide a colisão no MapLibre real, não symbol-sort-key sozinho (medido no e2e:
        # test_prioridade_classe_a_vence_b_em_colisao — o layer que vem DEPOIS vence). prioridade=1
        # (A/lavoura, mais importante) por isso fica por ÚLTIMO na lista, não na ordem declarada.
        assert rotulos[-1]["filter"] == ["==", ["get", "classe_uso"], "lavoura"]
        assert rotulos[0]["filter"] == ["==", ["get", "classe_uso"], "pastagem"]
        assert rotulos[-1]["layout"]["symbol-sort-key"] == -1
        assert rotulos[0]["layout"]["symbol-sort-key"] == -2
        assert rotulos[0]["id"] != rotulos[1]["id"]
        _valida_style_spec(doc)

    def test_permitir_sobreposicao_liga_allow_overlap(self):
        pc = _pc_ponto(
            {"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "permitir_sobreposicao": True}]}
        )
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["layout"]["text-allow-overlap"] is True

    def test_sem_classes_e_recusado(self):
        with pytest.raises(EstiloInvalido):
            compilador.compilar(_pc_ponto({"visivel": True, "classes": []}))


class TestPosicaoAncoraDeslocamento:
    def test_ancora_e_deslocamento_default_e_explicito(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}}]})
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["layout"]["text-anchor"] == "center"
        assert doc["layers"][-1]["layout"]["text-offset"] == [0, 0]

        pc2 = _pc_ponto(
            {
                "visivel": True,
                "classes": [{"texto": {"campo": "classe_uso"}, "ancora": "top-left", "deslocamento": [0.6, 0.6]}],
            }
        )
        doc2 = compilador.compilar(pc2)
        assert doc2["layers"][-1]["layout"]["text-anchor"] == "top-left"
        assert doc2["layers"][-1]["layout"]["text-offset"] == [0.6, 0.6]


class TestLinhaAoLongo:
    def _pc_linha(self, rotulos):
        return {
            "tipo": "unico",
            "geometria": "linha",
            "campo": None,
            "campos": ["nome"],
            "simbolo": {"cor": "#333333"},
            "rotulos": rotulos,
        }

    def test_ao_longo_da_linha_liga_symbol_placement_line(self):
        pc = self._pc_linha(
            {"visivel": True, "classes": [{"texto": {"campo": "nome"}, "ao_longo_da_linha": True, "repetir_px": 250}]}
        )
        doc = compilador.compilar(pc)
        rotulo = [la for la in doc["layers"] if la["type"] == "symbol"][0]
        assert rotulo["layout"]["symbol-placement"] == "line"
        assert rotulo["layout"]["symbol-spacing"] == 250.0
        _valida_style_spec(doc)

    def test_sem_ao_longo_nao_liga_symbol_placement(self):
        pc = self._pc_linha({"visivel": True, "classes": [{"texto": {"campo": "nome"}}]})
        doc = compilador.compilar(pc)
        rotulo = [la for la in doc["layers"] if la["type"] == "symbol"][0]
        assert "symbol-placement" not in rotulo["layout"]


class TestVariasLinhasEFonteEHalo:
    def test_varias_linhas_largura_max(self):
        pc = _pc_ponto(
            {"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "varias_linhas_largura_max": 6}]}
        )
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["layout"]["text-max-width"] == 6.0

    def test_fonte_padrao_e_explicita(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}}]})
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["layout"]["text-font"] == ["Noto Sans Regular"]

        pc2 = _pc_ponto(
            {"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "fonte": ["Open Sans Regular"]}]}
        )
        doc2 = compilador.compilar(pc2)
        assert doc2["layers"][-1]["layout"]["text-font"] == ["Open Sans Regular"]

    def test_halo(self):
        pc = _pc_ponto(
            {"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "halo_cor": "#ffffff", "halo_largura": 2}]}
        )
        doc = compilador.compilar(pc)
        assert doc["layers"][-1]["paint"]["text-halo-color"] == "#ffffff"
        assert doc["layers"][-1]["paint"]["text-halo-width"] == 2.0


class TestFaixaDeEscala:
    def test_escala_min_max_viram_maxzoom_minzoom_nativos(self):
        # escala_min (denominador MENOR = mais perto) -> maxzoom nativo; escala_max (MAIOR = mais
        # longe) -> minzoom nativo (ver app/estilos/compilador.py::_escala_para_zoom).
        pc = _pc_ponto(
            {"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}, "escala_min": 5000, "escala_max": 500000}]}
        )
        doc = compilador.compilar(pc)
        layer = doc["layers"][-1]
        assert layer["minzoom"] < layer["maxzoom"]
        assert layer["metadata"]["plat:escala_min"] == 5000
        assert layer["metadata"]["plat:escala_max"] == 500000

    def test_sem_faixa_nao_grava_minzoom_maxzoom(self):
        pc = _pc_ponto({"visivel": True, "classes": [{"texto": {"campo": "classe_uso"}}]})
        doc = compilador.compilar(pc)
        layer = doc["layers"][-1]
        assert "minzoom" not in layer and "maxzoom" not in layer
