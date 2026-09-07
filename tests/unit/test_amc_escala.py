"""Contrato de escala do motor multicritério (item L3-16-desempenho-escala), sem relógio.

O que este arquivo prova, cláusula por cláusula do portão:

- o pico de RAM de um bloco NÃO cresce com o total de unidades (é o que sustenta afirmar um teto de RAM
  para 1 milhão de células sem medir 1 milhão), e o modelo de memória não SUBESTIMA o pico real medido;
- o plano recusa, antes de começar, o que não cabe: unidades demais, fatores demais, bloco maior que o
  orçamento — sempre com código e mensagem, nunca cortando em silêncio;
- o navegador e o servidor decidem no MESMO número onde a combinação roda, e o navegador RECUSA acima
  dele (o `unidades_demais_para_o_navegador` do JavaScript é executado de verdade por node aqui);
- o job de recombinação é pesado (1 por vez na máquina) e pede memória dentro do orçamento.

Os tempos ficam em tests/unit/test_amc_escala_desempenho.py, que mede com a carga da máquina ao lado."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app import limites
from app.amc import escala
from app.amc.combinacao import Resultado

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "web" / "js" / "amc" / "combinacao.js"
TAMANHOS = (10_000, 100_000, 1_000_000)
FATORES = 15


def _js_disponivel() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _no_js(codigo: str, entrada: dict) -> dict:
    r = subprocess.run(["node", "--input-type=module", "-e", codigo],
                       input=json.dumps(entrada), capture_output=True, text=True, timeout=120, cwd=ROOT, check=True)
    return json.loads(r.stdout)


# ------------------------------------------------------------------ plano e guardrail de memória

def test_pico_de_ram_do_bloco_nao_cresce_com_o_total_de_unidades():
    """A propriedade que sustenta o guardrail: multiplicar o conjunto por 10 multiplica o número de BLOCOS,
    nunca o pico. Abaixo do tamanho de um bloco o pico é MENOR (o bloco encolhe até o conjunto), nunca maior."""
    picos = {n: escala.plano(n, FATORES)["pico_estimado_mb"] for n in TAMANHOS}
    teto = escala.pico_estimado_mb(limites.AMC_BLOCO_UNIDADES, FATORES)
    assert max(picos.values()) == teto, picos
    assert picos[100_000] == picos[1_000_000] == teto, f"10x mais unidades mudou o pico: {picos}"
    assert picos[10_000] < teto, picos
    blocos = {n: escala.plano(n, FATORES)["n_blocos"] for n in TAMANHOS}
    assert blocos[10_000] < blocos[100_000] < blocos[1_000_000], blocos


def test_plano_de_um_milhao_por_quinze_fatores_cabe_no_orcamento_declarado():
    p = escala.plano(1_000_000, FATORES)
    assert p["n_unidades"] == 1_000_000
    assert p["bloco"] == limites.AMC_BLOCO_UNIDADES
    assert p["n_blocos"] == 20
    assert p["pico_estimado_mb"] <= p["orcamento_mb"]
    assert p["timeout_s"] == limites.AMC_EXTRACAO_TIMEOUT_S == 1800
    assert p["onde_combinar"] == "servidor"


def test_orcamento_e_o_menor_entre_o_teto_do_produto_e_o_teto_da_maquina():
    from app.settings import settings

    assert escala.orcamento_mb() == min(limites.AMC_EXTRACAO_MEMORIA_MB, settings.PLAT_WORKER_MEMORIA_MB)
    assert escala.orcamento_mb() <= 4096, "o guardrail do portão é 4 GB; nunca prometer mais"


def test_modelo_de_memoria_nao_subestima_o_pico_real_de_um_bloco():
    """O modelo de `pico_estimado_mb` é conferido contra a realidade: aloca um bloco cheio, combina, e
    compara o crescimento REAL de `ru_maxrss` com o que o modelo previu para a matriz. Estimativa que
    nunca foi conferida contra medida é palpite, e palpite não entra em portão."""
    bloco = limites.AMC_BLOCO_UNIDADES
    antes = escala.medir_pico_mb()
    rng = np.random.default_rng(316)
    m = rng.uniform(0.0, 100.0, size=(bloco, FATORES))
    m[rng.uniform(size=m.shape) < 0.1] = np.nan
    r = list(escala.combinar_em_blocos([([f"u{i}" for i in range(bloco)], m)], [1.0] * FATORES))
    assert len(r) == 1 and isinstance(r[0][1], Resultado)
    crescimento = max(0.0, escala.medir_pico_mb() - antes)
    previsto = escala.pico_estimado_mb(bloco, FATORES) - escala.BASE_MB
    assert crescimento <= previsto, (
        f"o modelo previu {previsto:.2f} MB para a matriz do bloco e o pico real cresceu {crescimento:.2f} MB; "
        "aumente COPIAS_DA_MATRIZ/BYTES_POR_UNIDADE_ID em app/amc/escala.py"
    )


@pytest.mark.parametrize(("n", "f", "codigo"), [
    (limites.AMC_UNIDADES_MAX + 1, 15, "unidades_demais"),
    (1000, escala.FATORES_MAX + 1, "fatores_demais"),
    (0, 15, "sem_unidades"),
    (1000, 0, "sem_fatores"),
])
def test_plano_recusa_com_codigo_o_que_nao_cabe(n, f, codigo):
    with pytest.raises(escala.ErroEscala) as e:
        escala.plano(n, f)
    assert e.value.codigo == codigo
    assert e.value.mensagem


def test_plano_recusa_bloco_que_nao_cabe_no_orcamento_em_vez_de_cortar_em_silencio():
    with pytest.raises(escala.ErroEscala) as e:
        escala.plano(1_000_000, 15, bloco=1_000_000, orcamento=256)
    assert e.value.codigo == "bloco_nao_cabe_no_orcamento"
    assert e.value.detalhe["pico_estimado_mb"] > e.value.detalhe["orcamento_mb"]


def test_fatores_max_vem_do_esquema_publicado_e_nao_de_um_numero_solto():
    esquema = json.loads((ROOT / "docs" / "esquemas" / "amc_modelo.v1.json").read_text(encoding="utf-8"))
    assert escala.FATORES_MAX == esquema["properties"]["fatores"]["maxItems"]


# ------------------------------------------------------------------ onde combinar: servidor e navegador

@pytest.mark.parametrize(("n", "onde"), [
    (1, "navegador"),
    (limites.AMC_COMBINAR_NAVEGADOR_MAX - 1, "navegador"),
    (limites.AMC_COMBINAR_NAVEGADOR_MAX, "navegador"),
    (limites.AMC_COMBINAR_NAVEGADOR_MAX + 1, "servidor"),
    (1_000_000, "servidor"),
])
def test_onde_combinar_tem_uma_fronteira_so(n, onde):
    d = escala.onde_combinar(n)
    assert d["onde"] == onde
    assert d["limite"] == limites.AMC_COMBINAR_NAVEGADOR_MAX
    assert str(n) in d["motivo"]


def test_o_limite_do_navegador_e_o_mesmo_numero_nos_dois_lados():
    fonte = JS.read_text(encoding="utf-8")
    achado = re.search(r"export const LIMITE_NAVEGADOR = (\d+);", fonte)
    assert achado, "web/js/amc/combinacao.js sem LIMITE_NAVEGADOR"
    assert int(achado.group(1)) == limites.AMC_COMBINAR_NAVEGADOR_MAX


@pytest.mark.skipif(not _js_disponivel(), reason="node ausente nesta máquina")
def test_navegador_recusa_acima_do_limite_e_manda_para_o_servidor():
    codigo = """
    import { combinar, ondeCombinar, LIMITE_NAVEGADOR } from './web/js/amc/combinacao.js';
    const linha = () => [50, 50, 50];
    const saida = {};
    for (const n of [LIMITE_NAVEGADOR, LIMITE_NAVEGADOR + 1]) {
      const fatores = Array.from({ length: n }, linha);
      try {
        const r = combinar(fatores, [1, 1, 1]);
        saida[n] = { erro: null, unidades: r.fav.length, onde: ondeCombinar(n).onde };
      } catch (e) {
        saida[n] = { erro: e.codigo, detalhe: e.detalhe, onde: ondeCombinar(n).onde };
      }
    }
    process.stdout.write(JSON.stringify(saida));
    """
    r = _no_js(codigo, {})
    no_limite = r[str(limites.AMC_COMBINAR_NAVEGADOR_MAX)]
    assert no_limite["erro"] is None and no_limite["unidades"] == limites.AMC_COMBINAR_NAVEGADOR_MAX
    assert no_limite["onde"] == "navegador"
    acima = r[str(limites.AMC_COMBINAR_NAVEGADOR_MAX + 1)]
    assert acima["erro"] == "unidades_demais_para_o_navegador"
    assert acima["detalhe"]["onde"] == "servidor" and acima["onde"] == "servidor"


# ------------------------------------------------------------------ combinação em blocos

def test_combinar_em_blocos_da_o_mesmo_resultado_que_combinar_de_uma_vez():
    from app.amc.combinacao import combinar

    rng = np.random.default_rng(31631)
    m = rng.uniform(0.0, 100.0, size=(2500, 7))
    m[rng.uniform(size=m.shape) < 0.15] = np.nan
    pesos = list(rng.uniform(0.1, 5.0, size=7))
    inteiro = combinar(m, pesos)
    ids = [f"u{i:05d}" for i in range(m.shape[0])]
    partes = [(ids[i:i + 400], m[i:i + 400]) for i in range(0, m.shape[0], 400)]
    fav, ordem = [], []
    for pedaco, r in escala.combinar_em_blocos(partes, pesos):
        ordem.extend(pedaco)
        fav.extend(r.fav.tolist())
    assert ordem == ids
    np.testing.assert_allclose(np.array(fav), inteiro.fav, rtol=0, atol=1e-12, equal_nan=True)


def test_bloco_com_identificadores_e_linhas_em_numero_diferente_e_recusado():
    with pytest.raises(escala.ErroEscala) as e:
        list(escala.combinar_em_blocos([(["a", "b"], np.zeros((3, 2)))], [1.0, 1.0]))
    assert e.value.codigo == "bloco_incoerente"


# ------------------------------------------------------------------ job pesado (base da refutação)

def test_job_de_recombinacao_e_pesado_e_pede_memoria_dentro_do_orcamento():
    import app.amc.tarefas  # noqa: F401 — importado pelo efeito: registra os tipos amc.* no REGISTRO
    from app.jobs.registro import REGISTRO

    t = REGISTRO["amc.recombinar"]
    assert t.pesado is True, "sem pesado=True a fila não serializa as execuções (refutação do item)"
    assert t.memoria_mb == escala.orcamento_mb() <= limites.AMC_EXTRACAO_MEMORIA_MB
    assert t.timeout_s == limites.AMC_EXTRACAO_TIMEOUT_S
    assert t.chave({"execucao_id": "abc"}) == "amc_recombinar:abc"
