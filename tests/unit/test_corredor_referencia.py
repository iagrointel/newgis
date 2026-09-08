"""Reprodução do trecho de referência do motor de traçado linear da casa (item L3-10-corredor-custo-minimo).

O portão de pronto do item é medido contra o motor de LT que já existia (`rs-coop/tracado-lt`): a superfície
composta por `app.amc.corredor.compor` tem de ser IGUAL BIT A BIT à superfície oficial da rodada
(`saida/superficie.npz`, só leitura), e a rota recalculada tem de cair a Hausdorff ≤ 100 m da rota oficial,
com o trecho de 382 km traçado em ≤ 10 s. As três afirmações são as cláusulas do portão; o instrumento é o
MESMO do script (`scripts/corredor_referencia.py`), chamado pela função `reproduzir` — cópia colada aqui ia
divergir do instrumento sem ninguém perceber.

O motor de referência vive FORA do repositório e não é copiado para cá: sem o diretório na máquina, a suíte
pula estes testes (skip com o motivo) — o portão continua medido, e o número fica em
`tests/medidas/L3-10-corredor-custo-minimo.json`. Marca `lento` porque a reprodução inteira passa de um
minuto (grade de 9,5 milhões de células) e medir tempo não cabe na rodada rápida do driver.
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# O caminho do motor de referência é desta máquina; PLAT_CORREDOR_REFERENCIA troca o diretório sem editar teste.
REF = Path(os.environ.get("PLAT_CORREDOR_REFERENCIA", "/home/dev/rs-coop/tracado-lt"))
SUPERFICIE = REF / "saida" / "superficie.npz"
PORTAO_SIN = REF / "saida" / "portao_sinuosidade.json"
INSTRUMENTO = ROOT / "scripts" / "corredor_referencia.py"
HAUSDORFF_MAX_M = 100.0
SEGUNDOS_MAX = 10.0

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module")
def instrumento():
    """O script de conferência carregado como módulo (não é pacote); falta de referência é skip, nunca erro."""
    if not (REF / "motor" / "route_v1.py").exists() or not SUPERFICIE.exists():
        pytest.skip(f"motor de referência da casa ausente nesta máquina ({REF})")
    spec = importlib.util.spec_from_file_location("corredor_referencia_instrumento", INSTRUMENTO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def reproducao(instrumento, medida):
    """A conferência inteira, UMA vez para o módulo (superfície + duas rotas + dois corredores)."""
    saida = instrumento.reproduzir(REF, SUPERFICIE)
    g = medida("L3-10-corredor-custo-minimo")
    g("referencia_superficie_igual_bit_a_bit", saida["superficie_igual_bit_a_bit"], "bool",
      "scripts/corredor_referencia.py --referencia rs-coop/tracado-lt --superficie saida/superficie.npz")
    g("referencia_hausdorff_m", saida["esparso"]["hausdorff_m"], "m",
      "rota recalculada (motor esparso) contra a rota oficial da rodada")
    g("referencia_382km_s", saida["esparso_com_janela"]["segundos"], "s",
      "rota com janela de 400 células; a reta entre as pontas mede "
      f"{saida['reta_entre_as_pontas_km']} km")
    g("referencia_sinuosidade", saida["esparso"]["sinuosidade"], "razão",
      "rota recalculada; limiar p90 das LTs construídas do SIGEL na casa = "
      f"{_limiar_sinuosidade()}")
    g("referencia_corredor_5pct_celulas", saida["corredor_5pct"]["celulas"], "células",
      "corredor-epsilon de 5 % sobre a superfície oficial")
    return saida


def _limiar_sinuosidade() -> str:
    """O limiar declarado da casa, LIDO do relatório da rodada (nunca digitado aqui)."""
    try:
        return str(json.loads(PORTAO_SIN.read_text(encoding="utf-8"))["limiar"]["valor"])
    except (OSError, KeyError, ValueError):
        return "indisponível"


def test_superficie_bit_a_bit(reproducao):
    """Cláusula: a composição da casa reproduz a superfície oficial CÉLULA a CÉLULA, e o veto também."""
    assert reproducao["superficie_igual_bit_a_bit"] is True, reproducao["maior_diferenca"]
    assert reproducao["maior_diferenca"] == 0.0
    assert reproducao["veto_igual"] is True
    assert reproducao["camadas_do_cache"] > 0, reproducao["camadas_sem_cache"]


def test_rota_oficial_a_100_m(reproducao):
    """Cláusula: a rota recalculada cai a Hausdorff ≤ 100 m (uma célula) da rota oficial, com o mesmo custo."""
    r = reproducao["esparso"]
    assert r["hausdorff_m"] <= HAUSDORFF_MAX_M, r
    assert r["celulas"] == r["celulas_da_rota_oficial"], r
    # a janela declarada não muda o resultado, só o tempo: mesmo custo, mesma quantidade de células
    j = reproducao["esparso_com_janela"]
    assert j["custo"] == r["custo"] and j["celulas"] == r["celulas"], (r, j)


def test_382_km_em_ate_10_s(reproducao):
    """Cláusula de tempo: o trecho de referência (reta entre as pontas ≈ 382 km) traçado em ≤ 10 s."""
    assert reproducao["reta_entre_as_pontas_km"] >= 380.0, "este não é o trecho de 382 km"
    assert reproducao["esparso_com_janela"]["segundos"] <= SEGUNDOS_MAX, \
        reproducao["esparso_com_janela"]["segundos"]


def test_sinuosidade_contra_o_limiar(reproducao):
    """Cláusula de sinuosidade: a rota reproduzida TEM a mesma sinuosidade da rota oficial (mesma geometria a
    100 m), e o número fica registrado contra o limiar p90 declarado da casa — que é limiar da rota OPTIMIZADA
    por compressão de amplitude, não do LCP bruto que este item reproduz; por isso é comparação REGISTRADA, e
    não aprovação."""
    assert reproducao["esparso"]["sinuosidade"] == pytest.approx(
        reproducao["sinuosidade_da_rota_oficial"], abs=1e-3), \
        (reproducao["esparso"]["sinuosidade"], reproducao["sinuosidade_da_rota_oficial"])
    assert reproducao["esparso"]["sinuosidade"] >= 1.0


def test_corredor_epsilon_contem_o_otimo(reproducao):
    """O corredor de 5 % nasce do custo ótimo recalculado, contém mais células que a rota e cresce com o epsilon."""
    r, f5, f10 = reproducao["esparso"], reproducao["corredor_5pct"], reproducao["corredor_10pct"]
    assert f5["otimo"] == pytest.approx(r["custo"], abs=0.01), (f5, r["custo"])
    assert f5["celulas"] >= r["celulas"]
    assert f5["celulas"] < f10["celulas"]
    assert f5["teto"] == pytest.approx(f5["otimo"] * 1.05, rel=1e-6)
