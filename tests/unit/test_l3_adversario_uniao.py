"""Adversário da LINHA L3 (motor AMC) sobre a base `wt/uniao` — achados do turno de 16/09/2026.

A suposição comum que caiu: vários itens marcados ENTREGUE nasceram em ramos (`wt/il3xx`) que nunca
foram de fato integrados a `wt/uniao`. Cada ramo, sozinho, passava nos próprios testes; a UNIÃO — a
base que vai para master — está com pedaços inteiros ausentes ou trocados por um decoy. Este arquivo
prova, um achado por teste, que o código que `wt/uniao` tem HOJE não é o que os ledgers descrevem.

Nasceram como @pytest.mark.xfail(strict=True) (achado do adversário, item ainda não consertado); o
turno de conserto (16/09/2026, item L3 do brief `linha-L3-laudo-adversario.md`) restaurou os cinco
pedaços que faltavam na união e removeu o xfail de cada teste que passou a XPASS de verdade — ver
os commits deste turno para o antes/depois de cada um. `test_registro_dos_achados_bate_com_o_laudo`
nunca foi xfail: só confere que o JSON de medidas do laudo original bate com os achados aqui.
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------- L3-02-c-smaa


def test_amc_smaa_registrado_como_job_pesado():
    from app.jobs import tipos

    assert "amc.smaa" in tipos.REGISTRO
    import app.amc.tarefas as amc_tarefas

    t = tipos.REGISTRO["amc.smaa"]
    assert t.funcao is amc_tarefas.amc_smaa
    assert t.pesado is True


# ---------------------------------------------------------------------- L3-16-desempenho-escala


def test_amc_recombinar_registrado_como_job():
    from app.jobs.registro import REGISTRO

    assert "amc.recombinar" in REGISTRO


# ---------------------------------------------------------------------- L3-15-metadado-fator
# (a ausência aqui também derruba a prova de equivalência do L3-01-j: o modelo de referência de
# tests/unit/test_amc_equivalencia_motor_referencia.py usa `versao_fonte` e falha por causa disto —
# ver test_l3_adversario_metodo_definicao abaixo.)


def _modelo_com_versao_fonte() -> dict:
    # Modelo completo (todo campo obrigatório do fator preenchido: id, nome, fonte, unidade, direcao,
    # base, camada, extrator, transformacao, peso — ver docs/esquemas/amc_modelo.v1.json e o helper
    # `fator()` de tests/unit/test_amc_metadado.py). Achado corrigido nesta rodada: a versão anterior
    # deste fixture só tinha os campos do próprio achado (versao_fonte) e violava OUTROS campos
    # obrigatórios que nada têm a ver com L3-15 — mascarava a prova, não a fazia.
    return {
        "esquema": "amc_modelo.v1",
        "nome": "modelo do adversário (versão de fonte)",
        "fatores": [
            {"id": "veg", "nome": "vegetação", "fonte": "camada de teste interno", "unidade": "fração",
             "direcao": "maior_melhor", "base": "engenharia",
             "camada": {"tipo": "acervo", "id": "x"},
             "extrator": {"tipo": "poligono_fracao_area"},
             "transformacao": {"tipo": "linear", "minimo": 0.0, "maximo": 1.0},
             "peso": 1.0,
             "versao_fonte": "coleção 10, lida em 2026-09"},
        ],
    }


def test_esquema_aceita_versao_fonte_do_metadado():
    from app.amc import esquema as mod_esquema

    assert mod_esquema.violacoes(_modelo_com_versao_fonte()) == []


def test_relatorio_aceita_definicao_para_listar_proxies():
    from app.amc import relatorio as mod_relatorio

    saida = mod_relatorio.montar_relatorio(
        [[10.0]], [1.0], ids_fatores=["veg"], definicao=_modelo_com_versao_fonte(),
    )
    assert "proxies" in saida["metadado"]


def test_tela_de_explicacao_tem_cartao_de_metadado():
    html = (RAIZ / "web" / "amc_explicacao.html").read_text(encoding="utf-8")
    assert 'id="metadado-cartao"' in html


# ---------------------------------------------------------------------- L3-14 / L3-07 (COALESCE)


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
