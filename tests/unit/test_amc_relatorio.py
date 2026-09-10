"""Testes do item L3-14-cobertura-dado-ausente: relatório mostra cobertura por fator."""

from __future__ import annotations

import pytest

from app.amc import relatorio as mod_relatorio


def test_relatorio_mostra_cobertura_por_fator_e_marca_abaixo_do_limiar():
    # fator "chuva": 70 unidades com dado, 30 sem (abaixo do limiar padrão 80%)
    fatores = [[60.0, 40.0] if i < 70 else [None, 40.0] for i in range(100)]
    pesos = [1.0, 1.0]

    saida = mod_relatorio.montar_relatorio(fatores, pesos, ids_fatores=["chuva", "solo"])

    assert saida["politica_ausente"] == "excluir"
    assert len(saida["cobertura_por_fator"]) == 2
    por_id = {c["id_fator"]: c for c in saida["cobertura_por_fator"]}
    assert por_id["chuva"]["fracao_unidades"] == pytest.approx(0.70)
    assert por_id["chuva"]["abaixo_do_limiar"] is True
    assert por_id["solo"]["fracao_unidades"] == pytest.approx(1.0)
    assert por_id["solo"]["abaixo_do_limiar"] is False
    assert saida["fatores_abaixo_do_limiar"] == ["chuva"]
    assert "chuva" in saida["aviso_cobertura"]
    assert "resultado" in saida and "fav" in saida["resultado"]


def test_relatorio_sem_fator_abaixo_do_limiar():
    fatores = [[60.0], [60.0], [60.0]]
    saida = mod_relatorio.montar_relatorio(fatores, [1.0])
    assert saida["fatores_abaixo_do_limiar"] == []
    assert "todos os" in saida["aviso_cobertura"]


def test_relatorio_declara_politica_ausente_sempre():
    fatores = [[60.0], [None]]
    for politica in ("excluir", "nulo", "pessimista"):
        saida = mod_relatorio.montar_relatorio(fatores, [1.0], politica_ausente=politica)
        assert saida["politica_ausente"] == politica
        assert saida["politica_ausente_descricao"]  # nunca vazio: é obrigatório declarar
