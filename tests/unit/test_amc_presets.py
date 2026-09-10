"""Contrato dos presets do motor multicritério (item L3-01-h-presets).

Cobre o módulo puro `app/amc/presets.py`: os cinco presets integrados (o 'pesos iguais' por
contrato do item, sempre presente), a validação do conteúdo (peso fora da lista, fator repetido,
soma de pesos zero, combinador desconhecido), a lista do que falta na aplicação, o veto por
unidade onde o fator de veto TEM dado, e o round-trip exportar -> importar. O adversário do item
(importar preset com fator que o modelo não tem) é recusado com a lista do que falta.
"""

import numpy as np
import pytest

from app.amc import presets as pres
from app.amc.combinacao import COMBINADORES, combinar

# ------------------------------------------------------------------ integrados


def test_pesos_iguais_existe_sempre_e_vale_para_qualquer_modelo():
    p = pres.integrado_por_id("pesos_iguais")
    assert p is not None and p["integrado"] is True
    assert p["conteudo"]["pesos_iguais"] is True
    # vale para qualquer matriz: peso 1 em todo fator, nunca recusa fator
    assert pres.fatores_faltando(p["conteudo"], ["qualquer_um"]) == []
    assert pres.pesos_da_matriz(p["conteudo"], ["a", "b", "c"]) == [1.0, 1.0, 1.0]


def test_os_quatro_exemplos_logisticos_sao_integrados_e_tem_pesos_somando_mais_que_zero():
    esperados = {"logistica_galpao", "logistica_ultima_milha",
                 "logistica_industria", "logistica_custo_minimo"}
    assert esperados <= set(pres.INTEGRADOS)
    for pid in esperados:
        p = pres.integrado_por_id(pid)
        assert p["integrado"] is True
        c = pres.validar_conteudo(p["conteudo"])
        assert sum(c["pesos"].values()) > 0
    # sem nome de cliente nos nomes de fator dos exemplos (regra da casa)
    for pid in esperados:
        for f in pres.INTEGRADOS[pid]["conteudo"]["fatores"]:
            assert f == f.lower() and " " not in f


def test_integrado_desconhecido_volta_none():
    assert pres.integrado_por_id("nao_existe") is None


def test_integrado_tem_os_cinco_por_contrato():
    assert len(pres.INTEGRADOS) == 5


# ------------------------------------------------------------------ validar_conteudo


def _conteudo(**trocas):
    base = {"fatores": ["acesso_rodoviario", "custo_terreno"],
            "pesos": {"acesso_rodoviario": 5.0, "custo_terreno": 2.0}}
    base.update(trocas)
    return base


def test_conteudo_valido_volta_normalizado_com_padroes():
    c = pres.validar_conteudo(_conteudo())
    assert c["pesos_iguais"] is False
    assert c["combinador"] == "soma_ponderada"
    assert c["politica_ausente"] == "excluir"
    assert c["gama"] == 0.5
    assert c["vetos"] == {}
    assert c["fatores"] == ["acesso_rodoviario", "custo_terreno"]


def test_nome_de_fator_e_cortado_e_validado():
    c = pres.validar_conteudo(_conteudo(fatores=["  acesso_rodoviario ", "custo_terreno"]))
    assert c["fatores"] == ["acesso_rodoviario", "custo_terreno"]
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(fatores=["a" * 200]))
    assert e.value.codigo == "fator_invalido"


def test_peso_fora_da_lista_e_recusado_com_a_faltando():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(pesos={"acesso_rodoviario": 1.0, "outro": 2.0}))
    assert e.value.codigo == "peso_fora_da_lista"
    assert e.value.detalhe["faltando"] == ["outro"]


def test_fator_repetido_e_recusado():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(fatores=["custo_terreno", "custo_terreno"]))
    assert e.value.codigo == "fator_duplicado"


def test_soma_de_pesos_zero_e_recusada():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(pesos={"acesso_rodoviario": 0.0, "custo_terreno": 0.0}))
    assert e.value.codigo == "soma_de_pesos_zero"


def test_peso_negativo_e_nao_numerico_sao_recusados():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(pesos={"acesso_rodoviario": -1.0, "custo_terreno": 2.0}))
    assert e.value.codigo == "peso_invalido"
    with pytest.raises(pres.ErroConteudo) as e2:
        pres.validar_conteudo(_conteudo(pesos={"acesso_rodoviario": "alto", "custo_terreno": 2.0}))
    assert e2.value.codigo == "peso_invalido"


def test_combinador_desconhecido_e_recusado_com_a_lista_de_aceitos():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(combinador="media_dourada"))
    assert e.value.codigo == "combinador_desconhecido"
    assert e.value.detalhe["aceitos"] == sorted(COMBINADORES)


def test_gama_fora_da_faixa_e_recusado():
    for ruim in (1.5, -0.1, "x"):
        with pytest.raises(pres.ErroConteudo) as e:
            pres.validar_conteudo(_conteudo(gama=ruim))
        assert e.value.codigo == "gama_invalido"


def test_pesos_iguais_nao_aceita_declarar_fatores():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo({"pesos_iguais": True, "fatores": ["a"], "pesos": {"a": 1.0}})
    assert e.value.codigo == "pesos_iguais_sem_fatores"


def test_veto_fora_da_lista_e_fora_da_faixa_sao_recusados():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo(_conteudo(vetos={"area_alagada": 1.0}))
    assert e.value.codigo == "veto_fora_da_lista"
    with pytest.raises(pres.ErroConteudo) as e2:
        pres.validar_conteudo(_conteudo(vetos={"custo_terreno": 2.0}))
    assert e2.value.codigo == "veto_invalido"


def test_preset_sem_fatores_orienta_para_pesos_iguais():
    with pytest.raises(pres.ErroConteudo) as e:
        pres.validar_conteudo({"pesos": {"a": 1.0}})
    assert e.value.codigo == "fatores_ausentes"
    assert "pesos_iguais" in e.value.mensagem


# ------------------------------------------------------------------ aplicação (sem job)


def test_fatores_faltando_da_a_lista_da_recusa():
    c = pres.validar_conteudo(_conteudo())
    assert pres.fatores_faltando(c, ["acesso_rodoviario"]) == ["custo_terreno"]
    assert pres.fatores_faltando(c, ["acesso_rodoviario", "custo_terreno"]) == []


def test_pesos_da_matriz_respeita_a_ordem_da_matriz():
    c = pres.validar_conteudo(_conteudo())
    assert pres.pesos_da_matriz(c, ["custo_terreno", "acesso_rodoviario"]) == [2.0, 5.0]
    with pytest.raises(pres.ErroConteudo) as e:
        pres.pesos_da_matriz(c, ["acesso_rodoviario", "custo_terreno", "extra"])
    assert e.value.codigo == "fator_fora_do_preset"


def test_veto_so_alcanca_unidade_onde_o_fator_de_veto_tem_dado():
    c = pres.validar_conteudo(_conteudo(
        fatores=["acesso_rodoviario", "custo_terreno", "area_alagada"],
        pesos={"acesso_rodoviario": 5.0, "custo_terreno": 2.0, "area_alagada": 0.0},
        vetos={"area_alagada": 1.0}))
    m = np.array([[80.0, 40.0, 5.0], [70.0, 30.0, np.nan]])
    fracao = pres.fracao_vetada_do_conteudo(c, m, ["acesso_rodoviario", "custo_terreno", "area_alagada"])
    assert fracao is not None
    assert fracao[0] == 1.0   # tem dado no fator de veto: vetada
    assert fracao[1] == 0.0   # sem dado no fator de veto: o veto não é inventado


def test_preset_sem_veto_devolve_none_e_combina_como_antes():
    c = pres.validar_conteudo(_conteudo())
    m = np.array([[80.0, 40.0]])
    assert pres.fracao_vetada_do_conteudo(c, m, ["acesso_rodoviario", "custo_terreno"]) is None
    pesos = pres.pesos_da_matriz(c, ["acesso_rodoviario", "custo_terreno"])
    r = combinar(m, pesos, combinador=c["combinador"], politica_ausente=c["politica_ausente"])
    assert r.fav[0] == pytest.approx((80.0 * 5.0 + 40.0 * 2.0) / 7.0)


def test_aplicar_pesos_iguais_sobre_matriz_qualquer():
    c = pres.integrado_por_id("pesos_iguais")["conteudo"]
    ids = ["f1", "f2", "f3"]
    m = np.array([[90.0, 30.0, 60.0], [10.0, 20.0, 30.0]])
    r = combinar(m, pres.pesos_da_matriz(c, ids), combinador=c["combinador"],
                 politica_ausente=c["politica_ausente"], ids_fatores=ids)
    assert r.fav[0] == pytest.approx((90.0 + 30.0 + 60.0) / 3.0)
    assert r.fav[1] == pytest.approx(20.0)


# ------------------------------------------------------------------ exportar / importar


def test_roundtrip_exportar_importar_preserva_o_preset():
    original = {
        "formato": pres.FORMATO, "versao": pres.VERSAO,
        "nome": "meu preset", "descricao": "teste", "escopo": "usuario",
        "conteudo": _conteudo(vetos={"custo_terreno": 0.5}),
    }
    doc = pres.documento_exportar(original)
    assert doc["formato"] == pres.FORMATO and doc["versao"] == pres.VERSAO
    valido = pres.documento_validar(doc)
    assert valido["nome"] == "meu preset"
    assert valido["conteudo"]["vetos"] == {"custo_terreno": 0.5}
    assert valido["faltando"] == []


def test_importacao_recusa_formato_versao_e_escopo_desconhecidos():
    base = {"formato": pres.FORMATO, "versao": pres.VERSAO, "nome": "x",
            "escopo": "usuario", "conteudo": _conteudo()}
    with pytest.raises(pres.ErroConteudo) as e:
        pres.documento_validar({**base, "formato": "outro/formato"})
    assert e.value.codigo == "formato_desconhecido"
    with pytest.raises(pres.ErroConteudo) as e2:
        pres.documento_validar({**base, "versao": 99})
    assert e2.value.codigo == "versao_desconhecida"
    with pytest.raises(pres.ErroConteudo) as e3:
        pres.documento_validar({**base, "escopo": "global"})
    assert e3.value.codigo == "escopo_invalido"


def test_adversario_importa_preset_com_fator_que_o_modelo_nao_tem_e_leva_a_lista():
    doc = {"formato": pres.FORMATO, "versao": pres.VERSAO, "nome": "armadilha",
           "escopo": "inquilino", "conteudo": _conteudo(),
           "fatores_modelo": ["acesso_rodoviario"]}
    with pytest.raises(pres.ErroConteudo) as e:
        pres.documento_validar(doc)
    assert e.value.codigo == "fator_fora_do_modelo"
    assert e.value.detalhe["faltando"] == ["custo_terreno"]


def test_importacao_sem_informar_modelo_aceita_e_declara_faltando_vazio():
    doc = {"formato": pres.FORMATO, "versao": pres.VERSAO, "nome": "sem modelo",
           "conteudo": _conteudo()}
    valido = pres.documento_validar(doc)
    assert valido["escopo"] == "usuario"  # padrão preenchido
    assert valido["faltando"] == []
