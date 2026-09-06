"""Prova do C6 (L2_CONCEITO.md): os dois avaliadores da linguagem de expressão — Python
(`app/expressao/avaliador_py.py`) e JavaScript (`web/js/expressao/avaliador.js`) — têm de concordar
byte a byte para os MESMOS vetores (`tests/expressoes/vetores.json`, ≥ 20 casos, compartilhados
com o L5-11 quando esse item existir). O runner do lado JavaScript é `tests/expressoes/
executar_js.mjs`, chamado por subprocesso — nenhum dos dois lados sabe do outro em tempo de
execução, só o teste compara.

Canonicalização: JSON não distingue inteiro de decimal; Python distingue (`json.dumps(5.0)` →
"5.0", `json.dumps(5)` → "5") e JavaScript não (todo número é `number`). Para a comparação ser
byte a byte de verdade sem que essa diferença de representação vire falso negativo, todo número
PY que tem parte fracionária zero vira `int` antes de serializar — é convenção do TESTE, não do
avaliador (o avaliador já normaliza a maior parte dos casos sozinho; isto é rede de segurança)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VETORES = ROOT / "tests" / "expressoes" / "vetores.json"
# Vetores acrescentados depois do ataque adversarial de 06/09 (laco/handoffs/T3/L2-10-c-ADVERSARIO.md):
# cada um é um caso em que os dois avaliadores DIVERGIAM porque a operação era entregue ao operador da
# língua. Ficam em arquivo separado para não mexer na contagem de 309 que o teste do adversário confere.
VETORES_CONVERGENCIA = ROOT / "tests" / "expressoes" / "vetores_convergencia.json"
RUNNER_JS = ROOT / "tests" / "expressoes" / "executar_js.mjs"

sys.path.insert(0, str(ROOT))
from app.expressao.avaliador_py import ErroExpressao, avaliar_texto  # noqa: E402


def _vetores() -> list[dict]:
    return json.loads(VETORES.read_text(encoding="utf-8")) + json.loads(
        VETORES_CONVERGENCIA.read_text(encoding="utf-8")
    )


def _canonicalizar(valor):
    if isinstance(valor, bool) or valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and valor.is_integer():
            return int(valor)
        return valor
    if isinstance(valor, list):
        return [_canonicalizar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _canonicalizar(v) for k, v in valor.items()}
    raise AssertionError(f"tipo fora do esperado nesta passagem: {type(valor)}")  # pragma: no cover


def _serializar(valor) -> str:
    return json.dumps(_canonicalizar(valor), ensure_ascii=False, sort_keys=True)


@pytest.fixture(scope="module")
def resultados_js() -> list[dict]:
    """1 processo Node para todos os vetores (rodar `node` uma vez por vetor seria N× o custo à
    toa). A correspondência com `_vetores()` é por POSIÇÃO — `executar_js.mjs` lê o mesmo arquivo
    e mapeia na mesma ordem, nunca pelo texto da expressão (duas linhas podem ter o MESMO texto com
    contexto diferente, como "SeNulo com valor presente"/"ausente" abaixo; casar pelo texto juntaria
    o resultado errado com o vetor errado)."""
    entrada = [{"entrada": v["entrada"], "contexto": v.get("contexto") or {}} for v in _vetores()]
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--stdin"],
        input=json.dumps(entrada, ensure_ascii=True),  # ensure_ascii: meia-substituta não codifica em UTF-8
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        check=True,
    )
    return json.loads(r.stdout)


def test_ao_menos_200_vetores_compartilhados():
    assert len(_vetores()) >= 200, "extensão do núcleo: ≥ 200 expressões nos dois avaliadores"


def test_vetores_de_convergencia_cobrem_as_quatro_convencoes_fixadas():
    """Os casos que o ataque adversarial de 06/09 achou divergindo viram vetor COMPARTILHADO: se
    alguém devolver o `%` ao operador da língua, a comparação de texto à unidade UTF-16, o `\\d` ao
    Python ou a data ao `timedelta`/`new Date`, estes reprovam nos dois lados."""
    vetores = json.loads(VETORES_CONVERGENCIA.read_text(encoding="utf-8"))
    assert len(vetores) >= 26
    entradas = " ".join(v["entrada"] for v in vetores)
    assert "%" in entradas and "Numero(" in entradas and "Ano(" in entradas and "Find(" in entradas


def test_vetores_e_resultados_js_no_mesmo_numero_e_ordem(resultados_js):
    vetores = _vetores()
    assert len(resultados_js) == len(vetores)
    assert [r["entrada"] for r in resultados_js] == [v["entrada"] for v in vetores]


@pytest.mark.parametrize("vetor", _vetores(), ids=lambda v: v["descricao"])
def test_python_bate_com_saida_esperada(vetor):
    resultado = avaliar_texto(vetor["entrada"], vetor.get("contexto") or {})
    assert _canonicalizar(resultado) == _canonicalizar(vetor["saida"]), vetor["entrada"]


@pytest.mark.parametrize("indice,vetor", list(enumerate(_vetores())), ids=[v["descricao"] for v in _vetores()])
def test_javascript_bate_com_saida_esperada(indice, vetor, resultados_js):
    item = resultados_js[indice]
    assert item["erro"] is None, f"{vetor['entrada']}: {item['erro']}"
    assert _canonicalizar(item["resultado"]) == _canonicalizar(vetor["saida"]), vetor["entrada"]


@pytest.mark.parametrize("indice,vetor", list(enumerate(_vetores())), ids=[v["descricao"] for v in _vetores()])
def test_python_e_javascript_concordam_byte_a_byte(indice, vetor, resultados_js):
    """A prova em si (portão do item-pai, C6): não compara com o vetor, compara UM avaliador
    contra o OUTRO — o texto JSON serializado tem de ser idêntico caractere a caractere."""
    py_resultado = avaliar_texto(vetor["entrada"], vetor.get("contexto") or {})
    js_item = resultados_js[indice]
    assert js_item["erro"] is None, f"{vetor['entrada']}: avaliador JS levantou {js_item['erro']}"
    py_json = _serializar(py_resultado)
    js_json = _serializar(js_item["resultado"])
    assert py_json == js_json, f"{vetor['entrada']}: python={py_json!r} javascript={js_json!r}"


def test_tabela_de_funcoes_igual_nos_dois_avaliadores():
    """A lista de nomes de função tem de ser a MESMA — uma função que existe só num lado dos dois
    avaliadores é o tipo de divergência que este item existe para impedir."""
    from app.expressao.avaliador_py import TABELA_FUNCOES

    r = subprocess.run(
        ["node", str(RUNNER_JS), "--nomes-funcoes"], capture_output=True, text=True, timeout=15, check=True
    )
    nomes_js = set(json.loads(r.stdout))
    nomes_py = set(TABELA_FUNCOES)
    assert nomes_js == nomes_py


def test_ast_exportada_e_reimportada_avalia_igual_nos_dois_lados():
    from app.expressao.avaliador_py import analisar, ast_de_json, ast_para_json
    from app.expressao.avaliador_py import avaliar as avaliar_py

    texto = "Se($area > 300, Concatenar('grande: ', Texto($area)), 'pequena')"
    contexto = {"area": 450.5}
    no = analisar(texto)
    d = ast_para_json(no)
    no2 = ast_de_json(d)
    assert avaliar_py(no, contexto) == avaliar_py(no2, contexto)

    # o MESMO JSON de AST, avaliado pelo lado JavaScript, chega ao mesmo valor
    script = f"""
import {{ astDeJson, avaliar }} from '{RUNNER_JS.parent.parent.parent / "web/js/expressao/avaliador.js"}';
const no = astDeJson({json.dumps(d)});
process.stdout.write(JSON.stringify(avaliar(no, {json.dumps(contexto)})));
"""
    arq = ROOT / "tests" / "expressoes" / "_tmp_ast_roundtrip.mjs"
    arq.write_text(script, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(arq)], capture_output=True, text=True, timeout=15, check=True)
        resultado_js = json.loads(r.stdout)
    finally:
        arq.unlink(missing_ok=True)
    assert _canonicalizar(resultado_js) == _canonicalizar(avaliar_py(no, contexto))


@pytest.mark.parametrize("indice,vetor", list(enumerate(_vetores())), ids=[v["descricao"] for v in _vetores()])
def test_ast_ida_e_volta_avalia_igual_em_todos_os_vetores(indice, vetor, resultados_js):
    """Portão "AST exportado e reimportado avalia igual", com os ≥ 200 vetores e não só com um exemplo:
    (1) Python: analisar → ast_para_json → json.dumps/loads → ast_de_json → avaliar == avaliar direto;
    (2) JavaScript: o mesmo caminho dentro do runner (`resultado_ida_e_volta`);
    (3) o JSON da AST exportada pelos dois lados é idêntico byte a byte (o que se grava no documento
    não depende de qual avaliador o gravou)."""
    from app.expressao.avaliador_py import analisar, ast_de_json, ast_para_json
    from app.expressao.avaliador_py import avaliar as avaliar_py

    contexto = vetor.get("contexto") or {}
    no = analisar(vetor["entrada"])
    d = ast_para_json(no)
    reimportada = ast_de_json(json.loads(json.dumps(d, ensure_ascii=False)))
    assert _serializar(avaliar_py(reimportada, contexto)) == _serializar(avaliar_py(no, contexto))
    js = resultados_js[indice]
    assert js["erro_ida_e_volta"] is None, f"{vetor['entrada']}: {js['erro_ida_e_volta']}"
    assert _serializar(js["resultado_ida_e_volta"]) == _serializar(js["resultado"])
    assert json.dumps(_canonicalizar(js["ast"]), sort_keys=True, ensure_ascii=False) == json.dumps(
        _canonicalizar(d), sort_keys=True, ensure_ascii=False
    ), f"{vetor['entrada']}: AST exportada difere entre Python e JavaScript"


def test_ast_exportada_pelo_python_reimportada_no_javascript_avalia_igual_em_todos_os_vetores(resultados_js):
    """Cruzado: a AST gravada pelo PYTHON (é o que o servidor grava no documento) é lida pelo
    JAVASCRIPT (é o que o navegador lê) — um processo Node para todos os vetores (`--stdin --ast`)."""
    from app.expressao.avaliador_py import analisar, ast_para_json

    vetores = _vetores()
    entrada = [
        {"entrada": v["entrada"], "contexto": v.get("contexto") or {}, "ast": ast_para_json(analisar(v["entrada"]))}
        for v in vetores
    ]
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--stdin", "--ast"], input=json.dumps(entrada, ensure_ascii=True),
        capture_output=True, text=True, timeout=30, cwd=str(ROOT), check=True,
    )
    saida = json.loads(r.stdout)
    assert len(saida) == len(vetores)
    for vetor, item, direto in zip(vetores, saida, resultados_js, strict=True):
        assert item["erro"] is None, f"{vetor['entrada']}: {item['erro']}"
        assert _serializar(item["resultado"]) == _serializar(direto["resultado"]), vetor["entrada"]


def test_erro_de_sintaxe_devolve_linha_e_coluna():
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto("1 + + 2", {})
    assert exc.value.detalhe.get("linha") == 1
    assert "coluna" in exc.value.detalhe
