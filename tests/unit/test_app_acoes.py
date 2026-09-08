"""Item L5-01-e-acoes-configuraveis: contrato dos widgets igual nos dois lados, regras novas do modelo
(`evento_incompativel`, `alvo_incompativel`, `gatilho_repetido`, condição CQL2) iguais em Python e node, referência
quebrada ao renomear um campo da fonte, e a refutação: 30 ações em cadeia (latência e recursão)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.app_modelo.contratos import CONTRATOS
from app.app_modelo.validar import validar_modelo

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "app" / "executar_js.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node ausente")


def _node(comando: str, stdin=None, *extra: str) -> dict:
    r = subprocess.run(["node", str(RUNNER), comando, *extra], input=json.dumps(stdin) if stdin else None,
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _ulid(n: int) -> str:
    return "01K5" + str(n).zfill(22)


def _corpo(mensagens: list, campos_mun=None) -> dict:
    F1, F2, V1, V2, V3, W_MAPA, W_TAB, W_GRAF, W_TXT = (_ulid(i) for i in range(101, 110))
    return {
        "nos": [
            {"id": W_MAPA, "tipo": "mapa", "configuracao": {"vista": V1}},
            {"id": W_TAB, "tipo": "tabela", "configuracao": {"vista": V2, "colunas": []}},
            {"id": W_GRAF, "tipo": "grafico", "configuracao": {"vista": V2, "campo": "uf"}},
            {"id": W_TXT, "tipo": "texto", "configuracao": {"texto": "x"}},
        ],
        "fontes": [
            {"id": F1, "nome": "municipios", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": campos_mun or [{"nome": "cod", "tipo": "inteiro"}, {"nome": "uf", "tipo": "texto"},
                                      {"nome": "geometria", "tipo": "geometria"}]},
            {"id": F2, "nome": "escolas", "origem": {"tipo": "embutida", "feicoes": []},
             "campos": [{"nome": "cod_mun", "tipo": "inteiro"}, {"nome": "escola", "tipo": "texto"}]},
        ],
        "vistas": [{"id": V1, "nome": "mapa", "fonte": F1}, {"id": V2, "nome": "lista", "fonte": F1},
                   {"id": V3, "nome": "escolas", "fonte": F2}],
        "mensagens": mensagens,
    }


NOMES = ("F1", "F2", "V1", "V2", "V3", "W_MAPA", "W_TAB", "W_GRAF", "W_TXT")
IDS = {k: _ulid(i) for i, k in enumerate(NOMES, start=101)}


def _regras(corpo: dict) -> tuple[list[str], list[str]]:
    py = sorted(e["regra"] for e in validar_modelo(corpo)[0])
    js = sorted(e["regra"] for e in _node("validar", {"corpo": corpo})["erros"])
    return py, js


def test_contrato_dos_widgets_igual_ao_registro_em_node():
    registro = _node("contratos")
    esperado = {k: {"eventos": list(v["eventos"]), "acoes": list(v["acoes"])} for k, v in CONTRATOS.items()}
    assert registro == esperado, {k: (registro.get(k), esperado.get(k)) for k in set(registro) | set(esperado)
                                  if registro.get(k) != esperado.get(k)}


def test_evento_que_a_origem_nao_emite_e_alvo_que_nao_aceita_sao_recusados_nos_dois_lados():
    corpo = _corpo([
        {"id": _ulid(1), "gatilho": {"origem": IDS["W_TXT"], "evento": "selecao_mudou"},  # texto não emite nada
         "acoes": [{"alvo": IDS["V2"], "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
        {"id": _ulid(2), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"},
         "acoes": [{"alvo": IDS["W_TXT"], "acao": "zoom", "parametros": {}}]},  # texto não aceita zoom
        {"id": _ulid(3), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"},
         "acoes": [{"alvo": IDS["V2"], "acao": "zoom", "parametros": {}}]},  # vista só aceita ação de dado
    ])
    py, js = _regras(corpo)
    assert py == js, (py, js)
    assert py.count("evento_incompativel") == 1 and py.count("alvo_incompativel") == 2, py


def test_gatilho_repetido_e_recusado_e_o_mesmo_gatilho_com_alvos_diferentes_nao():
    base = {"alvo": IDS["V2"], "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}
    corpo = _corpo([
        {"id": _ulid(1), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"}, "acoes": [base]},
        {"id": _ulid(2), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"}, "acoes": [dict(base)]},
        {"id": _ulid(3), "gatilho": {"origem": IDS["W_MAPA"], "evento": "clique"},
         "acoes": [{"alvo": IDS["W_GRAF"], "acao": "piscar", "parametros": {}}]},
    ])
    py, js = _regras(corpo)
    assert py == js == ["gatilho_repetido"], (py, js)


def test_condicao_cql2_valida_e_campo_inexistente_na_condicao():
    ok = _corpo([{"id": _ulid(1), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"},
                  "acoes": [{"alvo": IDS["V2"], "acao": "filtrar", "relacao": {"tipo": "mesma_fonte"},
                             "parametros": {"condicao": {"op": "=", "args": [{"property": "uf"}, "SP"]}}}]}])
    assert _regras(ok) == ([], [])
    ruim = json.loads(json.dumps(ok))
    ruim["mensagens"][0]["acoes"][0]["parametros"]["condicao"] = {"op": "=", "args": [{"property": "estado"}, "SP"]}
    py, js = _regras(ruim)
    assert py == js == ["campo_inexistente"], (py, js)


def test_renomear_campo_da_fonte_quebra_a_referencia_da_relacao_nos_dois_lados():
    """Refutação: relação por atributo cod -> cod_mun; depois a fonte renomeia `cod` para `codigo`: a mensagem
    fica com referência quebrada, nomeada, nos dois validadores (e o painel do construtor a marca)."""
    msg = [{"id": _ulid(1), "gatilho": {"origem": IDS["W_MAPA"], "evento": "selecao_mudou"},
            "acoes": [{"alvo": IDS["V3"], "acao": "filtrar", "parametros": {},
                       "relacao": {"tipo": "atributo", "campo_origem": "cod", "campo_alvo": "cod_mun",
                                   "operador": "in"}}]}]
    assert _regras(_corpo(msg)) == ([], [])
    renomeada = _corpo(msg, campos_mun=[{"nome": "codigo", "tipo": "inteiro"}, {"nome": "uf", "tipo": "texto"},
                                        {"nome": "geometria", "tipo": "geometria"}])
    py, js = _regras(renomeada)
    assert py == js == ["campo_inexistente"], (py, js)
    erro = validar_modelo(renomeada)[0][0]
    assert "cod" in erro["erro"] and erro["campo"].endswith(".relacao.campo_origem"), erro


def test_refutacao_30_acoes_em_cadeia_latencia_e_sem_recursao(medida):
    r = _node("cadeia", None, "30", "5000")
    assert r["vistas"] == 31 and r["mensagens"] == 30, r
    assert r["registros_ultima"] == r["registros_primeira"] == 3, r  # a seleção atravessa as 30 vistas
    assert r["cortes"] == 0 and r["avisos"] == [], r  # cadeia linear: nada a cortar
    assert r["disparos_por_volta"] == 30, r
    gravar = medida("L5-01-e-acoes-configuraveis")
    gravar("cadeia_30_acoes_p95_ms", r["p95_ms"], "ms",
           "node tests/app/executar_js.mjs cadeia 30 5000: seleção no mapa atravessa 30 vistas encadeadas "
           "(filtrar mesma_fonte), 100 voltas, 5.000 feições; p95 por volta (tests/unit/test_app_acoes.py)")
    gravar("cadeia_30_acoes_max_ms", r["max_ms"], "ms", "mesma medição, pior volta")
    gravar("cadeia_30_acoes_profundidade", r["profundidade_max"], "níveis",
           "maior profundidade da pilha de disparo observada (recursão do barramento) numa volta")
    assert r["p95_ms"] <= 100, r
    # ciclo fechado no fim da cadeia (30 -> 1): a validação AVISA (regra `ciclo`); no barramento a segunda passagem
    # por v1 recebe o MESMO filtro (idempotente, `definirFiltro` não reemite) — a volta para sozinha, sem estouro,
    # com o mesmo número de disparos da cadeia linear e a mesma seleção na ponta
    r2 = _node("cadeia", None, "30", "5000", "ciclo")
    assert "ciclo" in r2["avisos_validacao"], r2
    assert r2["disparos_por_volta"] <= 31 and r2["profundidade_max"] <= 32, r2
    assert r2["registros_ultima"] == 3 and r2["p95_ms"] <= 100, r2
