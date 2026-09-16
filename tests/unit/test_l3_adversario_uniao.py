"""Adversário da LINHA L3 (motor AMC) sobre a base `wt/uniao` — achados do turno de 16/09/2026.

A suposição comum que caiu: vários itens marcados ENTREGUE nasceram em ramos (`wt/il3xx`) que nunca
foram de fato integrados a `wt/uniao`. Cada ramo, sozinho, passava nos próprios testes; a UNIÃO — a
base que vai para master — está com pedaços inteiros ausentes ou trocados por um decoy. Este arquivo
prova, um achado por teste, que o código que `wt/uniao` tem HOJE não é o que os ledgers descrevem.

Todo teste aqui é @pytest.mark.xfail(strict=True): se algum destes voltar a passar sem que ninguém
tenha mexido de propósito, o CI acusa (o item foi consertado ou o achado era enganoso) — os dois
merecem investigação, nunca silêncio.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------- L3-02-c-smaa


@pytest.mark.xfail(
    strict=True,
    reason="app/amc/tarefas.py não define amc_smaa nem registra o tipo de job 'amc.smaa' na base "
           "wt/uniao (achado do adversário L3, 16/09): o próprio ledger do item já avisava 'Depende "
           "do ramo w...' (cortado) — o ramo que continha o job nunca chegou à união. Reproduz: "
           "tests/unit/test_amc_smaa.py::test_job_amc_smaa_esta_registrado falha com AttributeError "
           "'module app.amc.tarefas has no attribute amc_smaa' nesta mesma base.",
)
def test_amc_smaa_registrado_como_job_pesado():
    from app.jobs import tipos

    assert "amc.smaa" in tipos.REGISTRO
    import app.amc.tarefas as amc_tarefas

    t = tipos.REGISTRO["amc.smaa"]
    assert t.funcao is amc_tarefas.amc_smaa
    assert t.pesado is True


# ---------------------------------------------------------------------- L3-16-desempenho-escala


@pytest.mark.xfail(
    strict=True,
    reason="app/amc/tarefas.py não registra o tipo de job 'amc.recombinar' na base wt/uniao "
           "(achado do adversário L3, 16/09). Reproduz: "
           "tests/unit/test_amc_escala.py::test_job_de_recombinacao_e_pesado_e_pede_memoria_dentro_do_orcamento "
           "falha com KeyError 'amc.recombinar' nesta mesma base — o portão do item exige "
           "'recombinação em SQL para > 200 mil unidades' como job com orçamento de memória, e não há "
           "job nenhum com esse nome no código hoje.",
)
def test_amc_recombinar_registrado_como_job():
    from app.jobs.registro import REGISTRO

    assert "amc.recombinar" in REGISTRO


# ---------------------------------------------------------------------- L3-15-metadado-fator
# (a ausência aqui também derruba a prova de equivalência do L3-01-j: o modelo de referência de
# tests/unit/test_amc_equivalencia_motor_referencia.py usa `versao_fonte` e falha por causa disto —
# ver test_l3_adversario_metodo_definicao abaixo.)


def _modelo_com_versao_fonte() -> dict:
    return {
        "fatores": [
            {"id": "veg", "peso": 1.0, "camada": {"tipo": "acervo", "id": "x"},
             "extrator": {"tipo": "poligono_fracao_area"},
             "transformacao": {"tipo": "linear", "minimo": 0.0, "maximo": 1.0},
             "versao_fonte": "coleção 10, lida em 2026-09"},
        ],
        "combinador": {"tipo": "soma_ponderada_normalizada"},
    }


@pytest.mark.xfail(
    strict=True,
    reason="docs/esquemas/amc_modelo.v1.json não aceita o campo fatores[].versao_fonte na base "
           "wt/uniao (additionalProperties recusa) — o item L3-15-metadado-fator (ledger: 'Ramo "
           "wt/il315metada nasce de e9ecc378 (wt/il301dtrans), nao de master') nunca chegou à união. "
           "Reproduz: tests/unit/test_amc_metadado.py::test_versao_de_fonte_e_aceita_e_chega_a_ficha "
           "falha na mesma base.",
)
def test_esquema_aceita_versao_fonte_do_metadado():
    from app.amc import esquema as mod_esquema

    assert mod_esquema.violacoes(_modelo_com_versao_fonte()) == []


@pytest.mark.xfail(
    strict=True,
    reason="app/amc/relatorio.montar_relatorio não aceita o parâmetro `definicao` (metadado de "
           "proxy/âncora do item L3-15) na base wt/uniao: TypeError 'unexpected keyword argument "
           "definicao'. Reproduz: tests/unit/test_amc_metadado.py::test_relatorio_lista_proxies_e_ancoras "
           "falha na mesma base.",
)
def test_relatorio_aceita_definicao_para_listar_proxies():
    from app.amc import relatorio as mod_relatorio

    saida = mod_relatorio.montar_relatorio(
        [[10.0]], [1.0], ids_fatores=["veg"], definicao=_modelo_com_versao_fonte(),
    )
    assert "proxies" in saida


@pytest.mark.xfail(
    strict=True,
    reason="web/amc_explicacao.html não tem o cartão de metadado (id=metadado-cartao) do item "
           "L3-15-metadado-fator na base wt/uniao — o '?' do fator descrito no portão do item não "
           "existe na tela desta união. Reproduz: "
           "tests/unit/test_amc_metadado.py::test_tela_da_explicacao_tem_o_interrogacao_e_o_cartao_de_proxies "
           "falha na mesma base.",
)
def test_tela_de_explicacao_tem_cartao_de_metadado():
    html = (RAIZ / "web" / "amc_explicacao.html").read_text(encoding="utf-8")
    assert 'id="metadado-cartao"' in html


# ---------------------------------------------------------------------- L3-14 / L3-07 (COALESCE)


@pytest.mark.xfail(
    strict=True,
    reason="app/amc/agregacao.py:170 usa coalesce(t.area_vetada_m2, 0) sem estar na lista EXCECOES "
           "do scanner do item L3-14-cobertura-dado-ausente — o próprio portão do item ('varredura "
           "estática ... integrada ao make check') está vermelho hoje contra o código que o item "
           "L3-07-agregacao gravou. Ou a linha é uma exceção legítima e falta declará-la com o "
           "motivo (agregação feição->grade quando não há restrição tocando a feição: 0% vetado não "
           "é dado ausente), ou a linha é o defeito que o item L3-14 existe para pegar — dos dois "
           "jeitos, hoje ninguém decidiu, e o gate está quebrado. Reproduz: "
           "tests/unit/test_amc_sem_coalesce_zero.py::test_sem_coalesce_de_coluna_de_fator_para_zero "
           "falha na mesma base.",
)
def test_scanner_anti_coalesce_zero_esta_verde():
    from tests.unit.test_amc_sem_coalesce_zero import PADRAO_COALESCE_ZERO, _achados

    assert _achados(PADRAO_COALESCE_ZERO) == []


# ---------------------------------------------------------------------- referência para o laudo

ACHADOS_JSON = RAIZ / "tests" / "medidas" / "L3-adversario-uniao-achados.json"


def test_registro_dos_achados_bate_com_o_laudo():
    """Não é uma refutação de item: só garante que o arquivo de medidas do laudo (commitado ao lado
    deste teste) descreve os mesmos 5 achados acima, para quem só ler tests/medidas/ achar o mapa."""
    dados = json.loads(ACHADOS_JSON.read_text(encoding="utf-8"))
    ids = {a["item"] for a in dados["achados"]}
    assert ids == {"L3-02-c-smaa", "L3-16-desempenho-escala", "L3-15-metadado-fator",
                   "L3-01-j-equivalencia-motor-logistico", "L3-14-cobertura-dado-ausente",
                   "L3-01-h-presets"}
