"""Contrato do documento de método do motor AMC (item L3-01-i-exportacao-metodo).

Cobre o módulo puro `app/amc/metodo.py`: o documento canônico (modelo, transformações, camadas com
sha256 e contagem, entrada bruta, resultado, versão do motor, data, ressalvas), o hash canônico
estável, o round-trip de importação com o MESMO hash, a recusa do documento alterado (a refutação
do item: peso trocado = hash diferente = importação recusa) e as validações do modelo.
"""

import copy
import json

import pytest

from app.amc import metodo
from app.amc.combinacao import combinar

MODELO = {
    "fatores": ["acesso_rodoviario", "custo_terreno", "area_alagada"],
    "pesos": {"acesso_rodoviario": 5.0, "custo_terreno": 2.0, "area_alagada": 1.0},
    "vetos": {"area_alagada": 1.0},
    "combinador": "soma_ponderada",
    "politica_ausente": "excluir",
}
CAMADAS = [
    {"fator": "acesso_rodoviario", "nome": "distância a via pavimentada", "sha256": "a" * 64},
    {"fator": "custo_terreno", "nome": "valor do solo declarado"},
    {"fator": "area_alagada", "nome": "área alagada", "sha256": "b" * 64},
]
TRANSFORMACOES = {
    "acesso_rodoviario": "distância em km reclassificada por quebra natural em nota 0-100",
    "area_alagada": "fração da unidade em mancha de inundação vezes cem",
}
ENTRADA = {"matriz": [[80.0, 40.0, 5.0], [70.0, 20.0, None], [55.0, 60.0, 0.0], [40.0, 90.0, 2.0]]}
GERADO_EM = "2026-09-08T14:03:00Z"


def _fracao_vetada():
    # área alagada ≥ 5 veta a unidade inteira; sem dado não veta
    return [0.0 if v is None else 1.0 * (v >= 5.0) for v in (linha[2] for linha in ENTRADA["matriz"])]


def _resultado():
    return combinar(
        ENTRADA["matriz"],
        [MODELO["pesos"][f] for f in MODELO["fatores"]],
        fracao_vetada=_fracao_vetada(),
        ids_fatores=MODELO["fatores"],
    ).como_dicionario()


def _documento(**kwargs):
    return metodo.metodo_canonico(
        nome="método de teste do exportador",
        modelo=MODELO,
        camadas=CAMADAS,
        transformacoes=TRANSFORMACOES,
        entrada=ENTRADA,
        resultado=kwargs.get("sem_resultado") and None or _resultado(),
        gerado_em=GERADO_EM,
    )


# ---------------------------------------------------------------- documento canônico


def test_documento_canonico_traz_modelo_transformacoes_camadas_resultado_motor_e_hash():
    d = _documento()
    assert d["formato"] == metodo.FORMATO
    assert d["versao"] == metodo.VERSAO_DOCUMENTO
    assert d["nome"] == "método de teste do exportador"
    assert d["gerado_em"] == GERADO_EM
    assert d["motor"]["versao"] and d["motor"]["sha"]
    # modelo normalizado: pesos, normalizados, vetos, combinador e escala
    assert d["modelo"]["pesos"]["acesso_rodoviario"] == 5.0
    assert d["modelo"]["pesos_normalizados"]["custo_terreno"] == pytest.approx(0.25)
    assert d["modelo"]["vetos"] == {"area_alagada": 1.0}
    assert d["modelo"]["escala"] == {"min": 0.0, "max": 100.0}
    assert d["modelo"]["descricao_combinador"]
    assert d["modelo"]["descricao_politica"]
    # transformações declaradas por fator
    assert d["transformacoes"]["contagem"] == 2
    assert "reclassificada" in d["transformacoes"]["por_fator"]["acesso_rodoviario"]
    # camadas: contagem e sha256 por fator (a proveniência que o item pede no JSON)
    assert d["camadas"]["contagem"] == 3
    assert {c["fator"] for c in d["camadas"]["por_fator"]} == set(MODELO["fatores"])
    assert d["camadas"]["por_fator"][0]["sha256"] == "a" * 64
    # entrada bruta e resultado com cobertura
    assert d["entrada"]["unidades"] == 4
    assert d["entrada"]["cobertura_por_fator"]["custo_terreno"] == 1.0
    assert d["resultado"]["fav"][0] == 0.0 and d["resultado"]["vetado"][0] is True
    assert d["resultado"]["fav"][1] == 55.7143        # (5·70 + 2·20) / 7, fator sem dado sai
    assert d["resultado"]["fav"][2] == 49.375
    assert "restrição" in d["resultado"]["motivo"][0]
    # ressalvas obrigatórias do item
    assert any("pesos escolhidos" in r for r in d["ressalvas"])
    assert any("triagem: sinal, não prova" in r for r in d["ressalvas"])
    assert any("proxy" in r for r in d["ressalvas"])
    assert d["sha256"] and len(d["sha256"]) == 64


def test_camada_sem_sha256_gera_ressalva_de_proveniencia():
    d = metodo.metodo_canonico(
        nome="sem proveniência", modelo={"fatores": ["f"], "pesos": {"f": 1.0}},
        camadas=[{"fator": "f", "nome": "camada sem hash"}],
        entrada={"matriz": [[50.0]]}, gerado_em=GERADO_EM,
    )
    assert any("sha256" in r and "não está registrada" in r for r in d["ressalvas"])


def test_hash_e_estavel_e_independe_da_ordem_das_chaves():
    a = _documento()
    b = json.loads(json.dumps(a))
    assert metodo.hash_canonico(a) == metodo.hash_canonico(b) == a["sha256"]


def test_importar_documento_reimportado_recria_o_modelo_com_o_mesmo_hash():
    d = _documento()
    # ida e volta POR TEXTO, como um arquivo exportado e reimportado
    texto = json.dumps(d, ensure_ascii=False, indent=1)
    reimportado = metodo.importar_metodo(json.loads(texto))
    assert reimportado["sha256"] == d["sha256"]
    assert reimportado["modelo"]["pesos"] == d["modelo"]["pesos"]
    assert reimportado["transformacoes"] == d["transformacoes"]
    assert metodo.hash_canonico(reimportado) == d["sha256"]


# ---------------------------------------------------------------- refutação do item


def test_adversario_altera_um_peso_o_hash_muda_e_a_importacao_recusa():
    d = _documento()
    alterado = copy.deepcopy(d)
    alterado["modelo"]["pesos"]["custo_terreno"] = 9.0
    # o hash do método alterado É outro
    assert metodo.hash_canonico(alterado) != d["sha256"]
    # e a importação recusa o documento alterado com código estável
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.importar_metodo(alterado)
    assert e.value.codigo == "documento_alterado"
    assert e.value.detalhe["gravado"] == d["sha256"]
    assert e.value.detalhe["recalculado"] == metodo.hash_canonico(alterado)


def test_confere_pdf_recusa_pdf_de_modelo_anterior():
    sha = _documento()["sha256"]
    # como a extração devolve: as duas linhas de 32 separadas por quebra de linha
    texto_do_pdf_antigo = f"plat — método\nsha256 do método\n{sha[:32]}\n{sha[32:]}\n"
    novo = copy.deepcopy(_documento())
    novo["modelo"]["pesos"]["custo_terreno"] = 9.0
    novo["sha256"] = metodo.hash_canonico(novo)
    assert metodo.confere_pdf(texto_do_pdf_antigo, _documento()) is True
    # o PDF antigo NÃO vale para o método novo (peso alterado = hash diferente)
    assert metodo.confere_pdf(texto_do_pdf_antigo, novo) is False


# ---------------------------------------------------------------- validações


def test_validacoes_com_codigo_estavel():
    base = {"nome": "x", "modelo": {"fatores": ["a"], "pesos": {"a": 1.0}}, "gerado_em": GERADO_EM}
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "modelo": {**base["modelo"], "combinador": "inexistente"}})
    assert e.value.codigo == "combinador_desconhecido"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "modelo": {**base["modelo"], "pesos": {"a": -1.0}}})
    assert e.value.codigo == "peso_negativo"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "modelo": {**base["modelo"], "vetos": {"a": 1.5}}})
    assert e.value.codigo == "veto_fora_da_faixa"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "camadas": [{"fator": "outro", "nome": "x"}]})
    assert e.value.codigo == "camada_fora_do_modelo"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "camadas": [{"fator": "a", "nome": "x", "sha256": "xyz"}]})
    assert e.value.codigo == "sha256_invalido"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "transformacoes": {"outro": "texto"}})
    assert e.value.codigo == "transformacao_fora_do_modelo"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(**{**base, "entrada": {"matriz": [[200.0]]}})
    assert e.value.codigo == "valor_fora_da_escala"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.metodo_canonico(
            **{**base, "entrada": {"matriz": [[50.0], [50.0]]}, "resultado": {"fav": [1.0]}}
        )
    assert e.value.codigo == "resultado_incompativel"


def test_formato_e_versao_desconhecidos_na_importacao():
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.importar_metodo({"formato": "outro/formato", "versao": 1})
    assert e.value.codigo == "formato_desconhecido"
    d = _documento()
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.importar_metodo({**d, "versao": 99})
    assert e.value.codigo == "versao_desconhecida"
    with pytest.raises(metodo.ErroMetodo) as e:
        metodo.importar_metodo({**d, "sha256": "curto"})
    assert e.value.codigo == "sha256_invalido"


def test_numeros_do_documento_inclui_textos_e_chaves():
    d = _documento()
    numeros = metodo.numeros_do_documento(d)
    assert 5.0 in numeros                       # peso
    assert 2026.0 in numeros                    # ano dentro de gerado_em (texto)
    assert 256.0 in numeros                     # o "256" da chave "sha256"
    assert metodo.hash_canonico(d) == d["sha256"]
