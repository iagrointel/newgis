"""Ataque independente ao motor multicritério (itens L3-01-a e L3-01-b), parte sem banco.

Escrito por um agente que NÃO construiu o motor. Regra: cada teste ou prova que o produto se defende, ou expõe um
defeito. Os que expõem defeito ficam `xfail(strict=True)`: enquanto o defeito existir o teste é um xfail; no dia em
que for consertado o pytest acusa XPASS e o teste vira prova permanente.

Alvo aqui: o hash canônico (duas definições semanticamente iguais têm de dar o mesmo hash; duas diferentes, hashes
diferentes), a validação do documento (defeitos que o JSON Schema pode não pegar) e a escolha do CRS de trabalho.
"""

import copy
import json

import pytest

from app.amc import crs as mod_crs
from app.amc import esquema as mod_esquema
from app.erros import ErroAPI
from tests.api.amc import exemplos


def _violacao(definicao) -> str | None:
    """Cláusula da primeira violação, ou None se a definição foi aceita."""
    try:
        mod_esquema.validar(definicao)
        return None
    except ErroAPI as e:
        v = (e.detalhe or {}).get("violacoes") or []
        return v[0]["clausula"] if v else e.erro


# ================================================================ 1. hash canônico
def test_hash_nao_muda_com_a_ordem_das_chaves():
    """Defesa esperada: o hash é do JSON canônico (sort_keys), então reordenar chaves não cria versão nova."""
    m = exemplos.modelo_valido()
    embaralhado = json.loads(json.dumps({k: m[k] for k in reversed(list(m))}))
    assert mod_esquema.hash_modelo(embaralhado) == mod_esquema.hash_modelo(m)


def test_hash_muda_quando_o_documento_muda():
    m = exemplos.modelo_valido()
    outro = copy.deepcopy(m)
    outro["fatores"][0]["peso"] = m["fatores"][0]["peso"] + 1
    assert mod_esquema.hash_modelo(outro) != mod_esquema.hash_modelo(m)


# CONSERTADO em 06/09/2026 (achado 5 do laudo): o JSON canônico normaliza o número antes do hash — float com parte
# fracionária zero e magnitude < 2^53 vira inteiro (app.amc.esquema.normalizar_numeros, ADR 0016 §"normalização
# numérica"). Era: "3 e 3.0 são o mesmo número em JSON e dão hashes diferentes; reenviar o mesmo modelo com o peso
# escrito como inteiro cria uma versão nova que não mudou nada". A marca xfail(strict) saiu; o teste é prova.
def test_hash_igual_para_numeros_json_iguais_escritos_de_forma_diferente():
    m = exemplos.modelo_valido()
    inteiro = copy.deepcopy(m)
    inteiro["fatores"][0]["peso"] = 3
    real = copy.deepcopy(m)
    real["fatores"][0]["peso"] = 3.0
    assert mod_esquema.hash_modelo(inteiro) == mod_esquema.hash_modelo(real)


def test_chave_repetida_no_json_cru_some_sem_aviso_e_nao_muda_o_hash():
    """Achado (não é colisão de sha256, é da camada de parsing): dois textos JSON DIFERENTES viram o mesmo
    documento e o mesmo hash, porque `json.loads` fica com a última ocorrência da chave repetida. Quem manda
    `{"nome": "A", "nome": "B"}` não é avisado de que "A" foi descartado."""
    m = exemplos.modelo_valido()
    texto = json.dumps(m, ensure_ascii=False)
    alvo = '"nome": "modelo de teste interno"'
    assert alvo in texto
    texto_com_chave_repetida = texto.replace(alvo, '"nome": "MODELO FALSO", ' + alvo, 1)
    assert texto_com_chave_repetida != texto
    assert mod_esquema.hash_modelo(json.loads(texto_com_chave_repetida)) == mod_esquema.hash_modelo(m)


# ================================================================ 2. validação: o que o produto DEFENDE
@pytest.mark.parametrize("nome, muda, clausula_esperada", [
    ("peso NaN", lambda m: m["fatores"][0].__setitem__("peso", json.loads('{"v": NaN}')["v"]), "números finitos"),
    ("peso Infinity", lambda m: m["fatores"][0].__setitem__("peso", json.loads('{"v": Infinity}')["v"]),
     "números finitos"),
    ("peso como texto", lambda m: m["fatores"][0].__setitem__("peso", "0.5"), "$.fatores[0].peso: type"),
    ("id só difere na caixa", lambda m: m["fatores"][1].__setitem__("id", "Declividade"), "$.fatores[1].id: pattern"),
    ("id só difere por espaço", lambda m: m["fatores"][1].__setitem__("id", "declividade "),
     "$.fatores[1].id: pattern"),
    ("peso booleano", lambda m: m["fatores"][0].__setitem__("peso", True), "$.fatores[0].peso: type"),
    ("nota fora de 0-100", lambda m: m["fatores"][1]["transformacao"]["bandas"][0].__setitem__("nota", 101),
     "$.fatores[1].transformacao.bandas[0].nota: maximum"),
])
def test_defeito_recusado_com_422_e_a_clausula(nome, muda, clausula_esperada):
    m = exemplos.modelo_valido()
    muda(m)
    clausula = _violacao(m)
    assert clausula is not None, f"{nome}: o modelo foi ACEITO"
    assert clausula.startswith(clausula_esperada), (nome, clausula)


def test_percentual_com_soma_quase_100_usa_a_tolerancia_declarada():
    """0,9999999 de folga: dentro da tolerância declarada (0,01) passa, fora dela recusa. Sem 500 nos dois casos."""
    m = exemplos.modelo_valido()
    m["combinador"] = {"tipo": "percentual"}
    m["fatores"][0]["peso"], m["fatores"][1]["peso"] = 49.9999999, 50.0
    assert _violacao(m) is None
    m["fatores"][0]["peso"] = 49.0
    assert _violacao(m) == "combinador percentual: soma(fatores[].peso) = 100"


def test_aninhamento_profundo_nao_derruba_a_validacao():
    """`extrator.parametros` é `{"type": "object"}` sem teto: 5.000 níveis de aninhamento. O portão exige que isto
    nunca seja 500 — e não é: o documento é aceito (o teto real é o do corpo da requisição, 10 MiB)."""
    m = exemplos.modelo_valido()
    m["fatores"][0]["extrator"]["parametros"] = json.loads('{"a":' * 5000 + "1" + "}" * 5000)
    assert _violacao(m) is None
    assert len(mod_esquema.hash_modelo(m)) == 64


# ================================================================ 3. validação: o que o produto NÃO defende
# Cada linha era um documento ACEITO até 06/09/2026; desde o conserto do achado 2 todas dão 422 com a cláusula.
TRANSFORMACOES_INCOERENTES = {
    "linear com faixa invertida": {"tipo": "linear", "minimo": 30, "maximo": 0, "direcao": "crescente"},
    "linear com mínimo igual ao máximo": {"tipo": "linear", "minimo": 5, "maximo": 5},
    "faixas com notas a menos": {"tipo": "faixas", "quebras": [1, 2, 3, 4, 5], "notas": [0, 100]},
    "faixas com quebras fora de ordem": {"tipo": "faixas", "quebras": [5, 1, 3], "notas": [0, 10, 20, 30]},
    "degraus fora de ordem": {"tipo": "degraus", "bandas": [{"ate": 2000, "nota": 10}, {"ate": 500, "nota": 90}]},
    "função contínua sem nenhum parâmetro": {"tipo": "gaussiana"},
}


@pytest.mark.parametrize("nome", sorted(TRANSFORMACOES_INCOERENTES))
# CONSERTADO em 06/09/2026 (achado 2 do laudo): app.amc.esquema._violacoes_transformacao confere a coerência
# INTERNA da transformação (faixa invertida ou degenerada, len(notas) = len(quebras) + 1, quebras e bandas em ordem
# crescente, função contínua com pelo menos um parâmetro numérico). Era: "a transformação é validada só na FORMA
# (tipo e campos obrigatórios de 4 dos 16 tipos) e o documento incoerente entra no modelo e no hash sem uma única
# violação". A marca xfail(strict) saiu; os seis casos são prova.
def test_transformacao_incoerente_deveria_ser_recusada(nome):
    m = exemplos.modelo_valido()
    m["fatores"][0]["transformacao"] = TRANSFORMACOES_INCOERENTES[nome]
    assert _violacao(m) is not None, f"{nome}: aceito"


# ================================================================ 4. CRS de trabalho
def test_distorcao_de_area_tem_sinal_e_e_declarada():
    """No meridiano central o fator de escala é 0,9996: a área no plano é MENOR que a geodésica, logo negativa."""
    pontos = [(-51.0, -20.0), (-50.99, -20.0), (-50.99, -19.99), (-51.0, -19.99)]
    ficha = mod_crs.ficha_crs(pontos, (-51.0, -20.0, -50.99, -19.99), (-50.995, -19.995))
    assert ficha["srid_trabalho"] == 31982 and ficha["zona_utm"] == 22
    assert ficha["distorcao_area_max_pct"] < 0
    assert ficha["cruza_zonas_utm"] is False and ficha["avisos"] == []


def test_area_que_cruza_duas_zonas_declara_o_aviso():
    pontos = [(-49.0, -20.0), (-47.0, -20.0), (-47.0, -19.0), (-49.0, -19.0)]
    ficha = mod_crs.ficha_crs(pontos, (-49.0, -20.0, -47.0, -19.0), (-48.0, -19.5))
    assert ficha["cruza_zonas_utm"] is True
    assert ficha["zonas_utm_cobertas"] == [22, 23]
    assert ficha["avisos"], "cruzar zona sem aviso na ficha"


# CONSERTADO em 06/09/2026 (achado 3 do laudo): app.amc.crs.ficha_crs enumera TODAS as zonas do intervalo
# (range de zona(xmin) a zona(xmax), mais a do centróide). Era: "`zonas_utm_cobertas` é o conjunto {zona(xmin),
# zona(xmax), zona(centróide)} — as zonas do MEIO somem; uma área de -60° a -42° cobre 21, 22, 23 e 24 e a ficha
# declara três, dizendo ao leitor que a área 'cruza 3 zonas UTM'". A marca xfail(strict) saiu.
def test_zonas_utm_cobertas_lista_todas_as_zonas_da_area():
    pontos = [(-60.0, -20.0), (-42.0, -20.0), (-42.0, -19.0), (-60.0, -19.0)]
    ficha = mod_crs.ficha_crs(pontos, (-60.0, -20.0, -42.0, -19.0), (-51.0, -19.5))
    assert ficha["zonas_utm_cobertas"] == [21, 22, 23, 24], ficha["zonas_utm_cobertas"]


def test_fora_da_cobertura_sirgas_recusa_em_vez_de_inventar_crs():
    with pytest.raises(ValueError):
        mod_crs.ficha_crs([(2.0, 48.0)], (2.0, 48.0, 2.1, 48.1), (2.05, 48.05))
    with pytest.raises(ValueError):
        mod_crs.ficha_crs([(179.9, -20.0)], (179.9, -20.0, 179.99, -19.9), (179.95, -19.95))
