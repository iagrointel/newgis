"""Item L3-01-a: o JSON Schema `amc_modelo.v1` e o hash canônico, sem banco e sem API.

Cláusulas do portão provadas aqui: (1) modelo inválido devolve 422 com a CLÁUSULA violada, um caso por defeito
nomeado no portão (peso negativo, fator sem transformação, soma de pesos zero, fator duplicado); (2) o hash é o
sha256 do JSON canônico e NÃO depende da ordem em que as chaves foram escritas; (3) o mesmo hash sai do script
independente `scripts/amc_hash_independente.py`, que não importa este módulo.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.amc import esquema
from app.erros import ErroAPI
from tests.api.amc import exemplos

ROOT = Path(__file__).resolve().parents[2]


def test_esquema_publicado_e_valido_e_e_o_declarado():
    s = esquema.esquema()
    assert s["title"] == "amc_modelo.v1"
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert esquema.CAMINHO_ESQUEMA == ROOT / "docs" / "esquemas" / "amc_modelo.v1.json"
    esquema.validar(exemplos.modelo_valido())  # não levanta


@pytest.mark.parametrize("nome", sorted(exemplos.INVALIDOS))
def test_cada_defeito_do_portao_sai_com_a_clausula(nome):
    construir, clausula = exemplos.INVALIDOS[nome]
    with pytest.raises(ErroAPI) as e:
        esquema.validar(construir())
    assert e.value.status_code == 422 and e.value.erro == "modelo_invalido"
    clausulas = [v["clausula"] for v in e.value.detalhe["violacoes"]]
    assert any(clausula in c for c in clausulas), (nome, clausulas)
    for v in e.value.detalhe["violacoes"]:
        assert v["caminho"].startswith("$") and v["mensagem"]


def test_todas_as_violacoes_saem_juntas_nao_so_a_primeira():
    m = exemplos.modelo_valido()
    m["fatores"][0]["peso"] = -1.0
    m["fatores"][1]["id"] = m["fatores"][0]["id"]
    violacoes = esquema.violacoes(m)
    clausulas = " | ".join(v["clausula"] for v in violacoes)
    assert "peso >= 0" in clausulas and "id único" in clausulas


def test_combinador_percentual_exige_pesos_que_fecham_100():
    m = exemplos.modelo_valido()
    m["combinador"] = {"tipo": "percentual"}
    assert any("percentual" in v["clausula"] for v in esquema.violacoes(m))
    m["fatores"][0]["peso"], m["fatores"][1]["peso"] = 70, 30
    assert esquema.violacoes(m) == []


def test_campo_fora_do_esquema_e_recusado():
    m = exemplos.modelo_valido()
    m["fatores"][0]["gambiarra"] = 1
    assert any("additionalProperties" in v["clausula"] for v in esquema.violacoes(m))


def _normaliza_por_fora(v):
    """A normalização numérica do ADR 0016 reescrita aqui, sem importar app.amc.esquema: se a regra mudar de um
    lado só, o teste abaixo falha."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v == int(v) and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, dict):
        return {k: _normaliza_por_fora(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normaliza_por_fora(x) for x in v]
    return v


def test_hash_e_o_sha256_do_json_canonico_e_independe_da_ordem_das_chaves():
    m = exemplos.modelo_valido()
    esperado = hashlib.sha256(
        json.dumps(_normaliza_por_fora(m), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert esquema.hash_modelo(m) == esperado
    # e o documento GRAVADO (que é o que validar() devolve, já normalizado) recomputa o mesmo hash pela regra
    # simples, sem normalização nenhuma: é isso que mantém a auditoria por fora possível
    gravado = esquema.validar(m)
    assert hashlib.sha256(
        json.dumps(gravado, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest() == esperado
    embaralhado = json.loads(json.dumps(dict(reversed(list(m.items())))))
    assert esquema.hash_modelo(embaralhado) == esperado
    m["descricao"] = m["descricao"] + " "
    assert esquema.hash_modelo(m) != esperado


def test_script_independente_da_o_mesmo_hash(tmp_path):
    """O script não importa app.amc.esquema: se a regra do hash mudar de um lado só, este teste falha."""
    m = exemplos.modelo_valido()
    arquivo = tmp_path / "modelo.json"
    arquivo.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "amc_hash_independente.py"), "--arquivo", str(arquivo)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == esquema.hash_modelo(m)


def test_pesos_da_execucao_recusam_fator_desconhecido_e_soma_zero():
    m = exemplos.modelo_valido()
    assert esquema.validar_pesos(m, None) == {"declividade": 3.0, "dist_via": 1.5}
    assert esquema.validar_pesos(m, {"declividade": 1})["declividade"] == 1.0
    for pesos in ({"inexistente": 1}, {"declividade": -1}, {"declividade": 0, "dist_via": 0}):
        with pytest.raises(ErroAPI) as e:
            esquema.validar_pesos(m, pesos)
        assert e.value.status_code == 422 and e.value.erro == "pesos_invalidos"


# ================================================================ conserto do laudo L3-01-ADVERSARIO (06/09/2026)
TRANSFORMACOES_RECUSADAS = {
    "linear invertida": ({"tipo": "linear", "minimo": 30, "maximo": 0}, "transformacao: minimo < maximo"),
    "linear degenerada": ({"tipo": "linear", "minimo": 5, "maximo": 5}, "transformacao: minimo < maximo"),
    "faixas com notas a menos": ({"tipo": "faixas", "quebras": [1, 2, 3, 4, 5], "notas": [0, 100]},
                                 "transformacao faixas: len(notas) = len(quebras) + 1"),
    "faixas com notas a mais": ({"tipo": "faixas", "quebras": [1, 2], "notas": [0, 10, 20, 30]},
                                "transformacao faixas: len(notas) = len(quebras) + 1"),
    "quebras fora de ordem": ({"tipo": "faixas", "quebras": [5, 1, 3], "notas": [0, 10, 20, 30]},
                              "transformacao faixas: quebras em ordem crescente"),
    "quebras repetidas": ({"tipo": "faixas", "quebras": [1, 1], "notas": [0, 10, 20]},
                          "transformacao faixas: quebras em ordem crescente"),
    "degraus fora de ordem": ({"tipo": "degraus", "bandas": [{"ate": 2000, "nota": 10}, {"ate": 500, "nota": 90}]},
                              "transformacao degraus: bandas em ordem crescente de 'ate'"),
    "gaussiana sem parametro": ({"tipo": "gaussiana"}, "transformacao gaussiana: pelo menos um parâmetro"),
    "potencia com parametro de texto": ({"tipo": "potencia", "expoente": "2"},
                                        "transformacao potencia: parâmetro numérico"),
}


@pytest.mark.parametrize("nome", sorted(TRANSFORMACOES_RECUSADAS))
def test_transformacao_incoerente_sai_422_com_a_clausula(nome):
    """Achado 2 do laudo: até 06/09/2026 estes nove documentos entravam no modelo, ganhavam hash e só quebrariam
    (ou dariam nota errada em silêncio) quando o motor do item L3-01-d fosse executá-los."""
    transformacao, clausula = TRANSFORMACOES_RECUSADAS[nome]
    m = exemplos.modelo_valido()
    m["fatores"][0]["transformacao"] = transformacao
    with pytest.raises(ErroAPI) as e:
        esquema.validar(m)
    assert e.value.status_code == 422 and e.value.erro == "modelo_invalido"
    clausulas = [v["clausula"] for v in e.value.detalhe["violacoes"]]
    assert clausula in clausulas, (nome, clausulas)


TRANSFORMACOES_ACEITAS = {
    "linear normal": {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": "decrescente"},
    "linear com faixa negativa": {"tipo": "linear", "minimo": -30, "maximo": -5},
    "faixas certas": {"tipo": "faixas", "quebras": [1, 2, 3], "notas": [0, 30, 60, 100]},
    "faixas com uma quebra": {"tipo": "faixas", "quebras": [10], "notas": [100, 0]},
    "degraus em ordem": {"tipo": "degraus", "bandas": [{"ate": 500, "nota": 90}, {"ate": 2000, "nota": 10}]},
    "categoria": {"tipo": "categoria", "notas": {"a": 100, "b": 0}, "outros": None},
    "gaussiana com parametro": {"tipo": "gaussiana", "media": 10, "desvio": 2},
    "grande com minimo e maximo": {"tipo": "grande", "minimo": 0, "maximo": 100, "abaixo": 0, "acima": 100},
}


@pytest.mark.parametrize("nome", sorted(TRANSFORMACOES_ACEITAS))
def test_transformacao_coerente_continua_passando(nome):
    """A trava não pode endurecer demais: o que é legítimo tem de continuar entrando."""
    m = exemplos.modelo_valido()
    m["fatores"][0]["transformacao"] = TRANSFORMACOES_ACEITAS[nome]
    assert esquema.validar(m) is not None


def test_numero_inteiro_e_real_iguais_dao_o_mesmo_hash_e_a_mesma_versao():
    """Achado 5 do laudo: em JSON `3` e `3.0` são o mesmo número. Antes davam hashes diferentes, e reenviar o mesmo
    modelo com o peso escrito como inteiro criava uma versão nova que não mudara nada."""
    m = exemplos.modelo_valido()
    inteiro, real = json.loads(json.dumps(m)), json.loads(json.dumps(m))
    inteiro["fatores"][0]["peso"], real["fatores"][0]["peso"] = 3, 3.0
    assert esquema.hash_modelo(inteiro) == esquema.hash_modelo(real)
    assert esquema.canonico(inteiro) == esquema.canonico(real)
    # e o documento devolvido pela validação (que é o que vai ao banco) já sai normalizado
    assert esquema.validar(real)["fatores"][0]["peso"] == 3
    assert isinstance(esquema.validar(real)["fatores"][0]["peso"], int)


def test_normalizacao_numerica_nao_estraga_o_que_nao_e_inteiro():
    assert esquema.normalizar_numeros({"a": 0.5, "b": [True, False], "c": -0.0, "d": 1e30, "e": "3.0"}) == \
        {"a": 0.5, "b": [True, False], "c": 0, "d": 1e30, "e": "3.0"}
    # booleano nunca vira número (em Python True == 1, e um `is` mal escrito quebraria aqui)
    saida = esquema.normalizar_numeros({"b": True})
    assert saida["b"] is True


def test_normalizacao_numerica_aguenta_documento_muito_aninhado():
    """`extrator.parametros` é objeto livre no esquema e a validação aceita milhares de níveis: a normalização
    não pode estourar a pilha do Python (por isso é iterativa)."""
    fundo = json.loads('{"a":' * 5000 + "3.0" + "}" * 5000)
    assert len(esquema.hash_modelo(fundo)) == 64
