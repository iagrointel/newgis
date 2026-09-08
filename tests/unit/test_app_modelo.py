"""Item L5-07-fontes-vistas-mensagens, sem navegador: o validador Python (app/app_modelo/validar.py) e o do
navegador (web/js/app/modelo.js, via node) produzem as MESMAS listas de erro para os mesmos corpos; relação entre
fontes diferentes sem declaração é recusada, com tipos que não casam (texto × inteiro) é recusada, com relação
válida passa; CQL2-text e CQL2-JSON filtram igual; o barramento corta o ciclo A->B->A em uma volta e avisa;
o estado das vistas sobrevive à ida e volta pela URL; latência gatilho->ação p95 <= 100 ms com 10 mil feições
(medida gravada com a carga da máquina)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.app_modelo import validar as pv

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "app" / "executar_js.mjs"
ITEM = "L5-07-fontes-vistas-mensagens"

F1, F2, VA, VB, VC, W1, W2, W3, M1 = (f"01K5{str(i).zfill(22)}" for i in range(1, 10))


def _node(comando: str, stdin: dict | None = None, *extra: str) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node ausente")
    r = subprocess.run(["node", str(RUNNER), comando, *extra], input=json.dumps(stdin) if stdin else None,
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)


def _corpo(relacao=None, campos2=None, mensagens=None) -> dict:
    return {
        "nos": [
            {"id": W1, "tipo": "mapa", "configuracao": {"vista": VA}},
            {"id": W2, "tipo": "tabela", "configuracao": {"vista": VC, "colunas": []}},
        ],
        "ligacoes": [],
        "fontes": [
            {"id": F1, "nome": "municipios", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": [{"nome": "cod", "tipo": "inteiro"}, {"nome": "nome", "tipo": "texto"},
                        {"nome": "geometria", "tipo": "geometria"}]},
            {"id": F2, "nome": "escolas", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": campos2 or [{"nome": "cod_mun", "tipo": "inteiro"}, {"nome": "nome", "tipo": "texto"}]},
        ],
        "vistas": [{"id": VA, "nome": "A", "fonte": F1}, {"id": VC, "nome": "C", "fonte": F2}],
        "mensagens": mensagens if mensagens is not None else [
            {"id": M1, "gatilho": {"origem": W1, "evento": "selecao_mudou"},
             "acoes": [{"alvo": VC, "acao": "filtrar", "parametros": {}, "relacao": relacao}]},
        ],
    }


def _regras(erros): return sorted(e["regra"] for e in erros)


def test_sem_relacao_entre_fontes_diferentes_e_recusado_nos_dois_lados():
    corpo = _corpo(relacao=None)
    erros, _ = pv.validar_modelo(corpo)
    assert _regras(erros) == ["relacao_ausente"], erros
    assert "exigem relação declarada" in erros[0]["erro"]
    js = _node("validar", {"corpo": corpo})
    assert _regras(js["erros"]) == _regras(erros)


def test_tipo_do_campo_de_relacao_texto_x_inteiro_e_recusado():
    corpo = _corpo(relacao={"tipo": "atributo", "campo_origem": "nome", "campo_alvo": "cod_mun", "operador": "in"})
    erros, _ = pv.validar_modelo(corpo)
    assert _regras(erros) == ["relacao_tipos"], erros
    assert _regras(_node("validar", {"corpo": corpo})["erros"]) == ["relacao_tipos"]
    # inteiro x decimal é a exceção documentada: passa
    corpo = _corpo(relacao={"tipo": "atributo", "campo_origem": "cod", "campo_alvo": "cod_mun", "operador": "in"},
                   campos2=[{"nome": "cod_mun", "tipo": "decimal"}])
    assert pv.validar_modelo(corpo)[0] == []
    assert _node("validar", {"corpo": corpo})["erros"] == []


def test_relacao_valida_espacial_e_referencias_pendentes():
    corpo = _corpo(relacao={"tipo": "atributo", "campo_origem": "cod", "campo_alvo": "cod_mun", "operador": "in"})
    assert pv.validar_modelo(corpo)[0] == [] and _node("validar", {"corpo": corpo})["erros"] == []
    corpo = _corpo(relacao={"tipo": "espacial"})
    assert _regras(pv.validar_modelo(corpo)[0]) == ["relacao_espacial_sem_geometria"]  # escolas sem geometria
    corpo = _corpo(relacao={"tipo": "espacial"},
                   campos2=[{"nome": "cod_mun", "tipo": "inteiro"}, {"nome": "geometria", "tipo": "geometria"}])
    assert pv.validar_modelo(corpo)[0] == []
    corpo = _corpo(mensagens=[{"id": M1, "gatilho": {"origem": "01K50000000000000000000099", "evento": "clique"},
                               "acoes": [{"alvo": VA, "acao": "zoom"}]}])
    assert _regras(pv.validar_modelo(corpo)[0]) == ["referencia_pendente"]
    assert _regras(_node("validar", {"corpo": corpo})["erros"]) == ["referencia_pendente"]
    corpo = _corpo(mensagens=[{"id": M1, "gatilho": {"origem": W1, "evento": "sacudiu"},
                               "acoes": [{"alvo": VA, "acao": "explodir"}]}])
    assert _regras(pv.validar_modelo(corpo)[0]) == ["acao", "evento"]


def test_ciclo_e_aviso_nao_erro_e_o_barramento_corta_em_uma_volta():
    r = _node("ciclo")
    assert r["erros_validacao"] == [] and r["avisos_validacao"] == ["ciclo"]
    assert "ciclo_cortado" in r["avisos"] and r["cortes"] >= 1
    assert r["registrosB"] == 2 and r["registrosA"] == 1  # cod=1 -> escolas do 1 (2) -> município 1; e para


def test_cql2_texto_e_json_filtram_igual():
    feicoes = [{"type": "Feature", "id": i, "properties": {"n": i, "uf": u, "d": None if i == 3 else i * 1.5}}
               for i, u in enumerate(["SP", "RJ", "MG", "SP"], start=1)]
    filtros = ["uf = 'SP'", {"op": "=", "args": [{"property": "uf"}, "SP"]}, "n between 2 and 3", "d is null",
               "uf in ('RJ','MG') and n <> 2", "not uf like 'S%'", "n > 10", "campo ="]
    r = _node("cql2", {"filtros": filtros, "feicoes": feicoes})
    assert r[0]["ids"] == [1, 4] and r[1]["ids"] == [1, 4] and r[0]["json"] == r[1]["json"]
    assert r[2]["ids"] == [2, 3] and r[3]["ids"] == [3] and r[4]["ids"] == [3]
    assert r[5]["ids"] == [2, 3] and r[6]["ids"] == []
    assert r[7]["erro"] == "sintaxe"
    with pytest.raises(ValueError):
        pv.validar_cql2({"op": "explodir", "args": []})


def test_estado_das_vistas_na_url_ida_e_volta():
    r = _node("url")
    assert r["query"].startswith("item=x&v.") and r["aplicados"] == 1
    assert r["filtro"] == {"op": ">=", "args": [{"property": "k"}, 2]}
    assert r["selecao"] == [3] and r["registros"] == [2, 3]


def test_medida_latencia_gatilho_acao_10_mil_feicoes(medida):
    carga = os.getloadavg()[0]
    with open("/proc/meminfo", encoding="utf-8") as f:
        livre_kb = next(int(li.split()[1]) for li in f if li.startswith("MemAvailable"))
    r = _node("latencia", None, "10000")
    assert "erro" not in r, r
    assert r["acoes_grafico"] == 200
    gravar = medida(ITEM)
    gravar("latencia_gatilho_acao_p95_ms", r["p95_ms"], "ms",
           "node tests/app/executar_js.mjs latencia 10000: selecao no mapa -> vista da tabela refiltrada + piscar no"
           " grafico, 200 disparos, 10 mil feicoes em memoria")
    gravar("latencia_gatilho_acao_p50_ms", r["p50_ms"], "ms", "mesmo comando, mediana")
    gravar("latencia_gatilho_acao_max_ms", r["max_ms"], "ms", "mesmo comando, maximo")
    gravar("carga_1min", round(carga, 2), "load", "os.getloadavg()[0] no instante da medida")
    gravar("ram_livre_gb", round(livre_kb / 1024 / 1024, 2), "GB",
           "MemAvailable de /proc/meminfo no instante da medida")
    assert r["p95_ms"] <= 100, (r, carga)
