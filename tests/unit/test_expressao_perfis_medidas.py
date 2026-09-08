"""Grava `tests/medidas/L5-11-expressoes-no-navegador.json` (fixture `medida`, ADR 0001 seção 10).
Só escreve com `PLAT_GRAVAR_MEDIDAS=1`; sem a variável, roda como conferência e não suja a árvore.
Toda medida de TEMPO vai acompanhada da carga da máquina e da memória livre no instante — número de
desempenho sem a carga ao lado não vale como prova (regra do laço, 07/09)."""

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.expressao.avaliador_py import TABELA_FUNCOES  # noqa: E402
from app.expressao.perfis import PERFIS  # noqa: E402
from tests.unit.test_expressao_perfis import (  # noqa: E402
    VETORES,
    medir_corte_do_perfil_javascript_ms,
    medir_corte_do_perfil_python_ms,
)

ITEM = "L5-11-expressoes-no-navegador"
VETORES_EXPRESSAO = json.loads((RAIZ / "tests" / "expressoes" / "vetores.json").read_text(encoding="utf-8"))


def _carga_e_memoria() -> tuple[float, float]:
    carga = os.getloadavg()[0]
    livre_kb = 0
    for linha in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MemAvailable:"):
            livre_kb = int(linha.split()[1])
    return round(carga, 2), round(livre_kb / 1024 / 1024, 2)


def test_grava_medidas_do_item(medida):
    gravar = medida(ITEM)
    gravar("funcoes_da_linguagem", len(TABELA_FUNCOES), "funções", "len(TABELA_FUNCOES)")
    gravar("perfis_de_uso", len(PERFIS), "perfis", "len(PERFIS)")
    gravar(
        "vetores_de_expressao_python_e_javascript",
        len(VETORES_EXPRESSAO),
        "vetores",
        "len(tests/expressoes/vetores.json)",
    )
    gravar("vetores_de_perfil", len(VETORES), "vetores", "len(tests/expressoes/vetores_perfis.json)")
    gravar(
        "vetores_popup_igual_calculo_de_formulario",
        len([v for v in VETORES if v["perfil"] == "popup"]),
        "vetores",
        "test_mesma_expressao_no_popup_e_no_calculo_de_formulario_da_o_mesmo_valor",
    )
    codigo_py, ms_py = medir_corte_do_perfil_python_ms()
    codigo_js, ms_js = medir_corte_do_perfil_javascript_ms()
    assert codigo_py == codigo_js == "tempo_excedido"
    carga, ram = _carga_e_memoria()
    gravar(
        "tempo_corte_perfil_popup_python_ms",
        round(ms_py, 2),
        "ms",
        "test_expressao_sem_fim_e_cortada_pelo_orcamento_do_perfil_no_python",
    )
    gravar(
        "tempo_corte_perfil_popup_javascript_ms",
        round(ms_js, 2),
        "ms",
        "test_expressao_sem_fim_e_cortada_pelo_orcamento_do_perfil_no_javascript",
    )
    gravar("carga_1min", carga, "média de 1 min (12 núcleos)", "os.getloadavg()[0] no instante da medida")
    gravar("ram_livre_gb", ram, "GB", "MemAvailable de /proc/meminfo no instante da medida")
    assert len(TABELA_FUNCOES) >= 40
    assert len(VETORES_EXPRESSAO) >= 200
