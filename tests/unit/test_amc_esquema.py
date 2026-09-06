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


def test_hash_e_o_sha256_do_json_canonico_e_independe_da_ordem_das_chaves():
    m = exemplos.modelo_valido()
    esperado = hashlib.sha256(
        json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert esquema.hash_modelo(m) == esperado
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
