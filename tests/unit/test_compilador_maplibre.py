"""Unidade do compilador de expressão -> MapLibre (item L2-02-d-rotulos, app/expressao/
compilador_maplibre.py). Duas frentes: (1) o subconjunto compilável produz a expressão MapLibre
certa; (2) o subconjunto sem equivalente nativo levanta `NaoCompilavel` com motivo, nunca compila
"quase certo" — é o gatilho da coluna do servidor (app/estilos/rotulos_servidor.py), testado à
parte na identidade dos "dois modos" (mesma expressão, mesmo texto)."""

import pytest

from app.expressao.avaliador_py import analisar
from app.expressao.compilador_maplibre import NaoCompilavel, compilar


def _c(texto):
    return compilar(analisar(texto))


class TestCompila:
    def test_campo(self):
        assert _c("$area_ha") == ["get", "area_ha"]

    def test_literal_numero_texto_booleano_nulo(self):
        assert _c("42") == 42
        assert _c("'abc'") == "abc"
        assert _c("verdadeiro") is True
        assert _c("nulo") is None

    def test_aritmetica(self):
        assert _c("$a + $b") == ["+", ["get", "a"], ["get", "b"]]
        assert _c("$a - 1") == ["-", ["get", "a"], 1]
        assert _c("$a * 2") == ["*", ["get", "a"], 2]
        assert _c("$a / 2") == ["/", ["get", "a"], 2]

    def test_comparacao_e_logica(self):
        assert _c("$a > 0") == [">", ["get", "a"], 0]
        assert _c("$a == 1 && $b == 2") == ["all", ["==", ["get", "a"], 1], ["==", ["get", "b"], 2]]
        assert _c("$a == 1 || $b == 2") == ["any", ["==", ["get", "a"], 1], ["==", ["get", "b"], 2]]
        assert _c("!$a") == ["!", ["get", "a"]]

    def test_negativo_unario(self):
        assert _c("-$a") == ["-", 0, ["get", "a"]]

    def test_concatenar(self):
        assert _c("Concatenar('a', $b, 'c')") == [
            "concat",
            ["to-string", "a"],
            ["to-string", ["get", "b"]],
            ["to-string", "c"],
        ]

    def test_texto_maiuscula_minuscula(self):
        assert _c("Texto($a)") == ["to-string", ["get", "a"]]
        assert _c("Maiuscula($a)") == ["upcase", ["get", "a"]]
        assert _c("Minuscula($a)") == ["downcase", ["get", "a"]]

    def test_se_condicional(self):
        assert _c("Se($a > 0, 'pos', 'neg')") == ["case", [">", ["get", "a"], 0], "pos", "neg"]

    def test_senulo_ehnulo(self):
        assert _c("SeNulo($a, 0)") == ["coalesce", ["get", "a"], 0]
        assert _c("EhNulo($a)") == ["==", ["get", "a"], None]

    def test_absoluto_minimo_maximo(self):
        assert _c("Absoluto($a)") == ["abs", ["get", "a"]]
        assert _c("Minimo($a, $b)") == ["min", ["get", "a"], ["get", "b"]]
        assert _c("Maximo($a, $b)") == ["max", ["get", "a"], ["get", "b"]]

    def test_arredondar_zero_casas(self):
        assert _c("Arredondar($a)") == ["round", ["get", "a"]]

    def test_arredondar_com_casas(self):
        assert _c("Arredondar($a, 1)") == ["/", ["round", ["*", ["get", "a"], 10]], 10]

    def test_expressao_composta_realista(self):
        # a mesma que a identidade servidor/compilado usa em tests/unit/test_rotulos_servidor.py
        expr = _c("Concatenar(Maiuscula($classe_uso), ' - ', Texto($area_ha))")
        assert expr[0] == "concat"
        assert expr[1] == ["to-string", ["upcase", ["get", "classe_uso"]]]


class TestNaoCompila:
    @pytest.mark.parametrize(
        "texto",
        [
            "TextoNumero($a)",
            "TextoNumero($a, 1)",
            "TextoData($a)",
            "$a % 2",
            "$a ^ 2",
            "Trim($a)",
            "Left($a, 2)",
            "Split($a, ',')",
            "Floor($a)",
            "Sqrt($a)",
            "Weekday($a)",
            "Decode($a, 1, 'x', 'y')",
            "Lista(1, 2)",
            "Numero($a)",
            "Potencia($a, 2)",
            "AgoraUTC()",
        ],
    )
    def test_sem_equivalente_levanta_nao_compilavel(self, texto):
        with pytest.raises(NaoCompilavel):
            _c(texto)

    def test_motivo_e_texto_nao_vazio(self):
        with pytest.raises(NaoCompilavel) as exc:
            _c("TextoNumero($area_ha, 1)")
        assert exc.value.motivo
        assert "pt-BR" in exc.value.motivo or "milhar" in exc.value.motivo
