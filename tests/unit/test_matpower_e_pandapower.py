"""Conversores de rede equilibrada, sem banco (item L4-05-c-pandapower-e-matpower).

Cláusulas do portão provadas aqui:

* o arquivo pandapower tem uma `bus` por barra, uma `line` por trecho e um `trafo` por transformador do
  modelo — `test_contagem_bate_com_o_modelo`;
* o caso MATPOWER público (`case9` e `case30`) é LIDO pelo leitor da casa, com as matrizes completas —
  `test_ler_caso_publico`;
* barra sem coordenada sai sem geometria, nunca no ponto (0, 0) — `test_barra_sem_coordenada_fica_sem_geo`;
* o arquivo escrito é lido por `pandapower.from_json` e o fluxo de potência CONVERGE, e o caso `.m`
  escrito é lido por `pandapower.converter.from_mpc` e também converge — `test_fluxo_de_potencia_converge`
  (a medida vai para `tests/medidas/L4-05-c-pandapower-e-matpower.json`); sem pandapower na máquina o
  teste PULA com a razão escrita, e as demais cláusulas continuam valendo.

Refutação (papel adversário), provada aqui:
* `test_caso_com_valor_nao_numerico_e_recusado`, `test_caso_com_matriz_aberta_e_recusado` e
  `test_caso_com_coluna_de_menos_e_recusado`: o leitor recusa com a linha, em vez de completar o que falta;
* `test_perda_de_ferro_em_quilowatt`: a perda de ferro que o modelo guarda em POR CENTO da potência
  aparente sai em quilowatt, e não mil vezes maior (o erro que a primeira escrita deste conector tinha).
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.rede_utilidades import matpower, pandapower_rede

ITEM = "L4-05-c-pandapower-e-matpower"
MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / f"{ITEM}.json"
DADOS = Path(__file__).resolve().parents[1] / "dados"
# python com pandapower instalado. A plataforma NÃO importa pandapower (ver requirements.txt); a suíte
# usa o que houver: o próprio interpretador, um apontado por variável de ambiente, ou o ambiente
# separado que o laço mantém fora do repositório para não mexer na venv compartilhada.
CANDIDATOS_PYTHON = (
    os.environ.get("PLAT_PYTHON_PANDAPOWER"),
    sys.executable,
    "/home/dev/plataforma/laco/var/venv-pandapower/bin/python",
)


def modelo_de_teste() -> dict:
    """O mesmo modelo em memória que `opendss.montar_da_subrede` devolve, escrito à mão: três barras
    (duas de média tensão e uma de baixa), um trecho, um transformador, uma carga e uma geração."""
    return {
        "nome": "AL-TESTE", "ano": 2026, "subredes": ["s"],
        "barra_fonte": "b1", "kv_fonte": 13.8, "pu_fonte": 1.0, "codigo_tensao_nominal": "49",
        "barras": {"b1": 13.8, "b2": 13.8, "b3": 0.22},
        "linhas": [{"nome": "t0", "barra1": "b1", "barra2": "b2", "fases": [1, 2, 3],
                    "comprimento_km": 0.5, "condutor": "2-CA", "feicao_id": "f0"}],
        "trafos": [{"nome": "x0", "codigo": "TR-1", "barra_at": "b2", "barra_bt": "b3", "kva": 75.0,
                    "kv_bt": 0.22, "kv_at": 13.8, "fases": 3, "nos_at": ".1.2.3",
                    "nos_bt": ".1.2.3.0", "ligacao_at": "delta", "ligacao_bt": "wye",
                    "perda_ferro_pc": 0.2, "resistencia_pc": 1.2}],
        "cargas": [
            {"nome": "u0", "barra": "b3", "fases_nos": [1, 2, 3], "fases": 3, "ligacao": "wye",
             "kv": 0.22, "kw": 12.0, "fator_de_potencia": 0.92, "modelo": 1, "vminpu": 0.92,
             "vmaxpu": 1.25, "curva": "c1", "energia_mensal_medida": True},
            {"nome": "g0", "barra": "b3", "fases_nos": [1, 2, 3], "fases": 3, "ligacao": "wye",
             "kv": 0.22, "kw": -3.0, "fator_de_potencia": 1.0, "modelo": 5, "vminpu": 0.5,
             "vmaxpu": 1.5, "curva": "c1", "energia_mensal_medida": True},
        ],
        "curvas": {}, "chaves": [],
        "conferencia": {"nos_da_subrede": 3, "fusoes_por_chave_fechada": 0, "barras_esperadas": 3,
                        "trechos_da_subrede": 1, "trechos_sem_no_na_topologia": 0,
                        "linhas_esperadas": 1, "transformadores": 1, "cargas": 1,
                        "geracao_distribuida": 1},
    }


def _tabela(net: dict, nome: str) -> dict:
    return json.loads(net["_object"][nome]["_object"])


def _linha_da_tabela(net: dict, nome: str, i: int) -> dict:
    t = _tabela(net, nome)
    return dict(zip(t["columns"], t["data"][i], strict=True))


# --- cláusula: as contagens batem com o modelo -----------------------------------------------------

def test_contagem_bate_com_o_modelo():
    modelo = modelo_de_teste()
    net = pandapower_rede.montar_net(modelo)
    c = pandapower_rede.conferencia(modelo, net)
    assert c["bus"] == c["barras_esperadas"] == 3
    assert c["line"] == c["linhas_esperadas"] == 1
    assert c["trafo"] == c["transformadores_esperados"] == 1
    assert c["load"] == c["cargas_esperadas"] == 1
    assert c["sgen"] == c["geracao_distribuida_esperada"] == 1
    assert c["ext_grid"] == 1
    # a geração distribuída é a MESMA que o OpenDSS recebe como carga negativa: aqui entra positiva no sgen
    assert _linha_da_tabela(net, "sgen", 0)["p_mw"] == pytest.approx(0.003)
    assert _linha_da_tabela(net, "load", 0)["p_mw"] == pytest.approx(0.012)


def test_perda_de_ferro_em_quilowatt():
    """0,2 % de 75 kVA = 150 W = 0,15 kW. O erro que este teste tranca é escrever 150 kW."""
    net = pandapower_rede.montar_net(modelo_de_teste())
    assert _linha_da_tabela(net, "trafo", 0)["pfe_kw"] == pytest.approx(0.15)
    assert _linha_da_tabela(net, "trafo", 0)["vk_percent"] == pandapower_rede.VK_PERCENT_REFERENCIA


def test_barra_sem_coordenada_fica_sem_geo():
    """A barra sem coordenada sai com `geo` NULO. Ponto (0, 0) é uma coordenada real, no golfo da
    Guiné: escrevê-la faria a barra aparecer no mapa como se tivesse sido medida."""
    net = pandapower_rede.montar_net(modelo_de_teste(), {"b1": (-47.9292, -15.7801)})
    geos = [linha[_tabela(net, "bus")["columns"].index("geo")] for linha in _tabela(net, "bus")["data"]]
    assert sum(1 for g in geos if g is not None) == 1
    assert json.loads([g for g in geos if g][0])["coordinates"] == [-47.9292, -15.7801]
    assert all(g is None or "[0, 0]" not in g for g in geos)
    net_sem = pandapower_rede.montar_net(modelo_de_teste())
    assert all(linha[5] is None for linha in _tabela(net_sem, "bus")["data"])


def test_potencia_reativa_vem_do_fator_de_potencia():
    q = pandapower_rede._q_mvar(12.0, 0.92)
    assert q == pytest.approx(0.012 * math.tan(math.acos(0.92)), rel=1e-9)
    assert pandapower_rede._q_mvar(12.0, 1.0) == 0.0


# --- cláusula: o caso público é lido ---------------------------------------------------------------

@pytest.mark.parametrize("nome,barras,ramos", [("case9", 9, 9), ("case30", 30, 41)])
def test_ler_caso_publico(nome, barras, ramos):
    caso = matpower.ler_caso((DADOS / f"matpower_{nome}.m").read_text(encoding="utf-8"))
    assert caso["versao"] == "2"
    assert caso["baseMVA"] == 100.0
    assert len(caso["bus"]) == barras
    assert len(caso["branch"]) == ramos
    assert all(len(linha) >= len(matpower.COLUNAS_BUS) for linha in caso["bus"])
    assert all(len(linha) >= len(matpower.COLUNAS_BRANCH) for linha in caso["branch"])
    # exatamente uma barra de referência (type = 3) em cada caso público
    tipos = [matpower.coluna(b, matpower.COLUNAS_BUS, "type") for b in caso["bus"]]
    assert tipos.count(3.0) == 1


def test_escrita_e_leitura_do_caso_fecham():
    modelo = modelo_de_teste()
    caso = matpower.ler_caso(matpower.texto_do_caso(modelo))
    assert len(caso["bus"]) == 3 and len(caso["gen"]) == 1
    assert len(caso["branch"]) == 2                      # um trecho e um transformador
    fonte = [b for b in caso["bus"] if matpower.coluna(b, matpower.COLUNAS_BUS, "type") == 3]
    assert len(fonte) == 1
    # a demanda líquida da barra de baixa: 12 kW de carga menos 3 kW de geração
    pd = sum(matpower.coluna(b, matpower.COLUNAS_BUS, "Pd") for b in caso["bus"])
    assert pd == pytest.approx(0.009)


# --- refutação: o leitor recusa em vez de completar -------------------------------------------------

def test_caso_com_valor_nao_numerico_e_recusado():
    with pytest.raises(matpower.ErroMatpower) as e:
        matpower.ler_caso("mpc.baseMVA = 100;\nmpc.bus = [\n1 3 zero;\n];\n")
    assert e.value.codigo == "valor_nao_numerico" and e.value.linha == 3


def test_caso_com_matriz_aberta_e_recusado():
    with pytest.raises(matpower.ErroMatpower) as e:
        matpower.ler_caso("mpc.baseMVA = 100;\nmpc.bus = [\n1 3 0;\n")
    assert e.value.codigo == "matriz_nao_fechada" and e.value.linha == 2


def test_caso_com_coluna_de_menos_e_recusado():
    texto = (DADOS / "matpower_case9.m").read_text(encoding="utf-8")
    cortado = texto.replace("\t1\t3\t0\t0\t0\t0\t1\t1\t0\t345\t1\t1\t0.9999999999;", "\t1\t3\t0;")
    assert cortado != texto
    with pytest.raises(matpower.ErroMatpower) as e:
        matpower.ler_caso(cortado)
    assert e.value.codigo == "colunas_de_menos"


def test_caso_sem_matriz_e_recusado():
    with pytest.raises(matpower.ErroMatpower) as e:
        matpower.ler_caso("mpc.baseMVA = 100;\n")
    assert e.value.codigo == "matriz_ausente"


# --- cláusula: o fluxo de potência converge ---------------------------------------------------------

_PROVA = r"""
import json, sys
import pandapower as pp
from pandapower.converter.matpower.from_mpc import from_mpc
saida = {}
net = pp.from_json(sys.argv[1])
saida["json_bus"] = len(net.bus); saida["json_line"] = len(net.line)
saida["json_trafo"] = len(net.trafo); saida["json_load"] = len(net.load)
saida["json_sgen"] = len(net.sgen)
pp.runpp(net, numba=False)
saida["json_convergiu"] = bool(net["converged"])
saida["json_vm_pu_minimo"] = float(net.res_bus.vm_pu.min())
saida["json_vm_pu_maximo"] = float(net.res_bus.vm_pu.max())
saida["json_p_da_fonte_mw"] = float(net.res_ext_grid.p_mw.iloc[0])
try:
    caso = from_mpc(sys.argv[2], f_hz=60)
    pp.runpp(caso, numba=False)
    saida["mpc_convergiu"] = bool(caso["converged"])
    saida["mpc_bus"] = len(caso.bus)
    saida["mpc_vm_pu_minimo"] = float(caso.res_bus.vm_pu.min())
except Exception as e:                                        # noqa: BLE001
    saida["mpc_erro"] = f"{type(e).__name__}: {e}"
for nome, caminho in (("case9", sys.argv[3]), ("case30", sys.argv[4])):
    try:
        publico = from_mpc(caminho, f_hz=60)
        pp.runpp(publico, numba=False)
        saida[nome] = {"convergiu": bool(publico["converged"]), "bus": len(publico.bus),
                       "branch": len(publico.line) + len(publico.trafo) + len(publico.impedance)}
    except Exception as e:                                    # noqa: BLE001
        saida[nome] = {"erro": f"{type(e).__name__}: {e}"}
print(json.dumps(saida))
"""


def _python_com_pandapower():
    for candidato in CANDIDATOS_PYTHON:
        if not candidato or not shutil.which(candidato) and not os.path.exists(candidato):
            continue
        r = subprocess.run([candidato, "-c", "import pandapower"], capture_output=True, timeout=180)
        if r.returncode == 0:
            return candidato
    return None


def test_fluxo_de_potencia_converge():
    executavel = _python_com_pandapower()
    if executavel is None:
        pytest.skip("pandapower não está em nenhum python desta máquina "
                    "(PLAT_PYTHON_PANDAPOWER, o interpretador da suíte, nem o ambiente do laço): "
                    "a convergência do fluxo não foi medida; as demais cláusulas do item valem")
    modelo = modelo_de_teste()
    net = pandapower_rede.montar_net(modelo)
    with tempfile.TemporaryDirectory() as pasta:
        cam_json = os.path.join(pasta, "rede.json")
        cam_m = os.path.join(pasta, "caso.m")
        with open(cam_json, "w", encoding="utf-8") as f:
            f.write(pandapower_rede.texto(net))
        with open(cam_m, "w", encoding="utf-8") as f:
            f.write(matpower.texto_do_caso(modelo))
        r = subprocess.run(
            [executavel, "-c", _PROVA, cam_json, cam_m,
             str(DADOS / "matpower_case9.m"), str(DADOS / "matpower_case30.m")],
            capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    medido = json.loads(r.stdout.strip().splitlines()[-1])

    assert medido["json_convergiu"] is True, medido
    assert (medido["json_bus"], medido["json_line"], medido["json_trafo"]) == (3, 1, 1), medido
    assert (medido["json_load"], medido["json_sgen"]) == (1, 1), medido
    # 0,5 a 1,5 pu é folga larga de propósito: a cláusula é CONVERGIR, não bater um perfil de tensão
    assert 0.5 < medido["json_vm_pu_minimo"] <= medido["json_vm_pu_maximo"] < 1.5, medido
    assert medido["mpc_convergiu"] is True, medido
    assert medido["mpc_bus"] == 3, medido
    # o mesmo modelo escrito nas duas línguas dá a mesma tensão: a diferença fica em 1 %
    assert abs(medido["mpc_vm_pu_minimo"] - medido["json_vm_pu_minimo"]) < 0.01, medido
    assert medido["case9"]["convergiu"] is True and medido["case9"]["bus"] == 9, medido
    assert medido["case30"]["convergiu"] is True and medido["case30"]["bus"] == 30, medido

    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    registro = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {}
    registro["fluxo_de_potencia"] = {
        "medido_por": executavel,
        "pandapower_pinado_em_requirements": "3.5.4",
        **medido,
    }
    MEDIDAS.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
