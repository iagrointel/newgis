"""Refutação exigida pelo item L3-14-cobertura-dado-ausente: o adversário procura qualquer caminho
em que uma célula SEM raster (ausência) produza nota igual à de uma célula com valor 0 (medição).

Três frentes: (1) o extrator zonal devolve `valor=None`, nunca `0.0`, quando a unidade não toca o
raster; (2) a combinação, com cada política declarada, nunca confunde ausência com zero; (3) a
cobertura por fator nunca soma célula ausente como se fosse presença de valor zero.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.amc import cobertura as mod_cobertura
from app.amc import combinacao as mod_combinacao
from app.amc import zonal as mod_zonal


def test_extrator_zonal_unidade_fora_do_raster_devolve_none_nunca_zero():
    """`_uma_unidade` devolve {'valor': None, 'cobertura': 0.0} quando a janela não cruza o raster
    (app/amc/zonal.py) — nunca {'valor': 0.0, ...}, que se confundiria com medição real. Confere
    toda linha `return {...'cobertura': 0.0...}` do arquivo fonte: 'valor' tem de ser None nela."""
    import inspect
    import re

    fonte = inspect.getsource(mod_zonal)
    linhas_de_retorno_sem_dado = [
        linha for linha in fonte.splitlines()
        if re.search(r"return\s*\{", linha) and re.search(r"cobertura[\"']:\s*0\.0", linha)
    ]
    assert linhas_de_retorno_sem_dado, (
        "nenhuma linha de retorno de cobertura zero encontrada — a varredura mudou de alvo"
    )
    for linha in linhas_de_retorno_sem_dado:
        assert re.search(r"valor[\"']:\s*None", linha), (
            f"retorno de cobertura zero com valor numérico (não None): {linha!r}"
        )


@pytest.mark.parametrize("politica", ["excluir", "nulo"])
def test_unidade_so_com_ausencia_nunca_recebe_nota_igual_a_unidade_so_com_zero(politica):
    """Nas políticas 'excluir' e 'nulo' (as que NÃO se declaram estimativa), uma unidade com TODOS
    os fatores ausentes fica sem nota finita — nunca colapsa no mesmo número que uma unidade com
    todos os fatores MEDIDOS como zero. 'pessimista' fica de fora deste teste de propósito: por
    definição de produto (`POLITICAS_AUSENTE['pessimista']`) ela É a política que deliberadamente
    substitui ausência por zero, sempre rotulada como estimativa — não é o bug que este item veta."""
    fatores = [[None, None], [0.0, 0.0]]
    pesos = [1.0, 1.0]
    resultado = mod_combinacao.combinar(fatores, pesos, politica_ausente=politica)

    nota_ausente = resultado.fav[0]
    nota_medida_zero = resultado.fav[1]

    assert not np.isfinite(nota_ausente)
    # a unidade medida como zero de verdade É finita e É zero — o contraste prova que os dois
    # caminhos não colapsam no mesmo número por acidente de implementação
    assert nota_medida_zero == pytest.approx(0.0)


def test_pessimista_e_a_unica_politica_que_declara_zero_e_e_sempre_rotulada():
    """'pessimista' converte ausência em 0 de propósito (é o produto da política), mas isso só é
    aceitável porque o relatório é OBRIGADO a expor a descrição da política junto do número — ver
    `app.amc.relatorio.montar_relatorio`, testado em test_amc_relatorio.py. Aqui confere que a
    descrição registrada no dicionário do módulo nomeia 'estimativa pessimista' explicitamente."""
    descricao = mod_combinacao.POLITICAS_AUSENTE["pessimista"]
    assert "estimativa" in descricao and "pessimista" in descricao


def test_cobertura_nao_conta_ausente_como_presenca_de_zero():
    """Uma coluna toda ausente e uma coluna toda com valor 0.0 têm coberturas DIFERENTES — a
    ausência é 0 % de presença, o zero medido é 100 % de presença. Confundi-las seria o bug que
    este item existe para vetar."""
    linhas_ausente = [[None], [None], [None]]
    linhas_zero = [[0.0], [0.0], [0.0]]

    c_ausente = mod_cobertura.cobertura_por_fator(linhas_ausente, ["f"])[0]
    c_zero = mod_cobertura.cobertura_por_fator(linhas_zero, ["f"])[0]

    assert c_ausente.fracao_unidades == 0.0
    assert c_zero.fracao_unidades == 1.0
    assert c_ausente.fracao_unidades != c_zero.fracao_unidades
