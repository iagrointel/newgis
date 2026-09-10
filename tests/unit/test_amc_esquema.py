"""Item L3-01-a-modelo-dado — validação em duas camadas (app/amc/esquema.py) e hash canônico, sem banco.

Cobre as cláusulas do portão que são de validação de documento (peso negativo, fator sem transformação, soma
de pesos zero, fator duplicado) e o hash canônico (json.dumps sort_keys + separadores fixos)."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from app.amc import esquema

RAIZ = Path(__file__).resolve().parents[2]

MODELO_VALIDO = {
    "combinador": "soma_ponderada",
    "fatores": [
        {"id": "declividade", "criterio": "menor declive é melhor", "peso": 2,
         "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 45, "inverter": True}},
        {"id": "distancia_via", "criterio": "perto de via é melhor", "peso": 1,
         "transformacao": {"tipo": "faixas", "quebras": [500, 1500], "notas": [100, 60, 20]}},
    ],
}


def _copia(**sobrepor):
    d = copy.deepcopy(MODELO_VALIDO)
    for caminho, valor in sobrepor.items():
        alvo = d
        partes = caminho.split(".")
        for p in partes[:-1]:
            alvo = alvo[int(p)] if p.isdigit() else alvo[p]
        chave = partes[-1]
        if valor is esquema:  # sentinela "apagar"
            del alvo[chave]
        else:
            alvo[chave] = valor
    return d


# ------------------------------------------------------------------ o esquema publicado é válido e é o declarado
def test_esquema_publicado_e_valido_e_e_o_declarado():
    doc = esquema.esquema()
    jsonschema.Draft202012Validator.check_schema(doc)  # não levanta = meta-esquema válido
    assert doc["$id"] == "amc_modelo.v1"
    assert esquema.ARQUIVO_ESQUEMA == RAIZ / "docs" / "esquemas" / "amc_modelo.v1.json"
    assert esquema.ARQUIVO_ESQUEMA.exists()


def test_modelo_valido_nao_tem_erro():
    assert esquema.erros_estruturais(MODELO_VALIDO) == []
    assert esquema.erros_semanticos(MODELO_VALIDO) == []


# ------------------------------------------------------------------ as quatro cláusulas inegociáveis do portão
def test_peso_negativo_e_a_clausula():
    d = _copia(**{"fatores.0.peso": -1})
    erros = esquema.erros_estruturais(d)
    assert any(e["clausula"] == "fatores[].peso >= 0" for e in erros), erros


def test_fator_sem_transformacao_e_a_clausula():
    d = _copia(**{"fatores.0.transformacao": esquema})  # sentinela: apaga a chave
    erros = esquema.erros_estruturais(d)
    assert any(e["clausula"] == "fatores[].transformacao obrigatória" for e in erros), erros


def test_soma_de_pesos_zero_e_a_clausula():
    d = _copia(**{"fatores.0.peso": 0, "fatores.1.peso": 0})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "soma(fatores[].peso) > 0" for e in erros), erros


def test_fator_duplicado_e_a_clausula():
    d = _copia()
    d["fatores"].append(dict(d["fatores"][0]))  # mesmo id "declividade"
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "fatores[].id único" for e in erros), erros


@pytest.mark.parametrize("peso", [float("nan"), float("inf"), float("-inf")])
def test_peso_nao_finito_e_recusado(peso):
    # NaN/Infinity são instâncias de float (passam no "type": "number" do JSON Schema); só a camada
    # semântica pega — é o achado do laudo do rascunho anterior ("peso NaN e Infinity: números finitos").
    d = _copia(**{"fatores.0.peso": peso})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "fatores[].peso >= 0" for e in erros), erros


def test_peso_como_texto_e_recusado():
    d = _copia(**{"fatores.0.peso": "0.5"})
    erros = esquema.erros_estruturais(d)
    assert any("fatores[].peso" in e["clausula"] or "peso" in e["campo"] for e in erros), erros


def test_id_invalido_por_caixa_ou_espaco_e_recusado():
    for ruim in ("Declividade", "declividade ", "123x", ""):
        d = _copia(**{"fatores.0.id": ruim})
        assert esquema.erros_estruturais(d), f"id {ruim!r} deveria violar o pattern"


# ------------------------------------------------------------------ coerência da transformação (bônus, fila de
# conserto §2 do laudo do rascunho anterior: não deixar entrar documento que o executor não vai conseguir rodar)
def test_faixa_invertida_e_recusada():
    d = _copia(**{"fatores.0.transformacao": {"tipo": "linear", "minimo": 30, "maximo": 0}})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "transformacao.linear: minimo < maximo" for e in erros), erros


def test_faixa_degenerada_minimo_igual_maximo_e_recusada():
    d = _copia(**{"fatores.0.transformacao": {"tipo": "linear", "minimo": 10, "maximo": 10}})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "transformacao.linear: minimo < maximo" for e in erros), erros


def test_faixas_quebras_fora_de_ordem_e_recusada():
    d = _copia(**{"fatores.1.transformacao": {"tipo": "faixas", "quebras": [1500, 500], "notas": [100, 60, 20]}})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "transformacao.faixas: quebras em ordem crescente" for e in erros), erros


def test_faixas_notas_incompativel_com_quebras_e_recusada():
    d = _copia(**{"fatores.1.transformacao": {"tipo": "faixas", "quebras": [500, 1500], "notas": [100, 20]}})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "transformacao.faixas: len(notas) == len(quebras) + 1" for e in erros), erros


def test_degraus_fora_de_ordem_e_recusada():
    d = _copia(**{"fatores.0.transformacao": {
        "tipo": "degraus", "bandas": [{"ate": 60, "nota": 30}, {"ate": 15, "nota": 100}, {"ate": 45, "nota": 50}],
    }})
    erros = esquema.erros_semanticos(d)
    assert any(e["clausula"] == "transformacao.degraus: bandas em ordem crescente de ate" for e in erros), erros


def test_gaussiana_sem_parametro_utilizavel_e_recusada_na_estrutura():
    d = _copia(**{"fatores.0.transformacao": {"tipo": "gaussiana"}})
    erros = esquema.erros_estruturais(d)
    assert erros, "gaussiana sem media/desvio deveria violar 'required'"


# ------------------------------------------------------------------ hash canônico
def test_hash_e_sha256_de_json_canonico():
    esperado = hashlib.sha256(
        json.dumps(MODELO_VALIDO, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert esquema.hash_canonico(MODELO_VALIDO) == esperado


def test_hash_e_deterministico_e_sensivel_a_ordem_de_chave_nao_ao_texto():
    a = {"combinador": "soma_ponderada", "fatores": MODELO_VALIDO["fatores"]}
    b = {"fatores": MODELO_VALIDO["fatores"], "combinador": "soma_ponderada"}  # chaves em outra ordem no dict
    assert esquema.hash_canonico(a) == esquema.hash_canonico(b)


def test_hash_muda_quando_documento_muda():
    a = esquema.hash_canonico(MODELO_VALIDO)
    b = esquema.hash_canonico(_copia(**{"fatores.0.peso": 3}))
    assert a != b


# ------------------------------------------------------------------ script independente (roda como subprocesso
# de verdade: não importa app.amc.esquema, prova que a fórmula está reimplementada, não só reexportada)
def test_script_independente_da_o_mesmo_hash(tmp_path):
    arq = tmp_path / "m.json"
    arq.write_text(json.dumps(MODELO_VALIDO), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "amc_hash_independente.py"), "--arquivo", str(arq)],
        capture_output=True, text=True, check=True, cwd=RAIZ,
    )
    assert r.stdout.strip() == esquema.hash_canonico(MODELO_VALIDO)


def test_script_independente_reimplementa_sem_importar_app_amc():
    linhas_import = [
        ln.strip() for ln in (RAIZ / "scripts" / "amc_hash_independente.py").read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    assert not any("app.amc" in ln or "app.catalogo" in ln for ln in linhas_import), linhas_import
