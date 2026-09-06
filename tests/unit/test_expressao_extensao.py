"""Contrato de coleções, erros e limites nos dois runtimes, sem consultar implementação para o oráculo."""

import json
import subprocess
import time
from pathlib import Path

import pytest

from app.expressao.avaliador_py import ErroExpressao, avaliar_texto

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/expressoes/executar_js.mjs"

ERROS = [
    ("Left('abc',-1)", {}, "tipo_invalido"),
    ("Right('abc',0.5)", {}, "tipo_invalido"),
    ("Mid('abc',verdadeiro)", {}, "tipo_invalido"),
    ("Find(1,'abc')", {}, "tipo_invalido"),
    ("Split('abc',1)", {}, "tipo_invalido"),
    ("Sqrt(-1)", {}, "numero_invalido"),
    ("Floor('1')", {}, "tipo_invalido"),
    ("Contagem(1)", {}, "tipo_invalido"),
    ("Primeiro('abc')", {}, "tipo_invalido"),
    ("Ultimo(1)", {}, "tipo_invalido"),
    ("Obter(Lista(1),-1)", {}, "tipo_invalido"),
    ("Obter(Lista(1),'0')", {}, "tipo_invalido"),
    ("Obter($x,1)", {"x": {"1": 3}}, "tipo_invalido"),
    ("Obter($x,'constructor')", {"x": {}}, "campo_nao_permitido"),
    ("Obter($x,'__proto__')", {"x": {}}, "campo_nao_permitido"),
    ("Obter($x,'prototype')", {"x": {}}, "campo_nao_permitido"),
    ("Contem(1,2)", {}, "tipo_invalido"),
    ("Soma(Lista(1,verdadeiro))", {}, "tipo_invalido"),
    ("Media(Lista('2',1))", {}, "tipo_invalido"),
    ("Juntar(Lista(Lista(1)))", {}, "tipo_invalido"),
    ("Unicos(2)", {}, "tipo_invalido"),
    ("Reverter('abc')", {}, "tipo_invalido"),
    ("Decode(1,1,2)", {}, "aridade_invalida"),
    ("Decode(1,1,2,3,4)", {}, "aridade_invalida"),
    ("Obter(Lista(1),0,1/0)", {}, "divisao_por_zero"),
    ("Potencia(2,1000000000)", {}, "numero_invalido"),
    ("2^1000000000", {}, "numero_invalido"),
    ("Potencia(-1,0.5)", {}, "numero_invalido"),
    ("Potencia(0,-1)", {}, "numero_invalido"),
    ("Arredondar(1,1000000000)", {}, "numero_invalido"),
    ("$x", {"x": [0] * 1025}, "valor_grande"),
    ("$x", {"x": "a" * 20001}, "valor_grande"),
    ("Concatenar($x,$x)", {"x": "a" * 11000}, "valor_grande"),
    ("Split($x,'')", {"x": "a" * 1025}, "valor_grande"),
    ("Replace($x,'a',$x)", {"x": "a" * 1000}, "valor_grande"),
    ("Obter($negado,'a')", {}, "campo_nao_permitido"),
    ("TextoNumero('1',2)", {}, "tipo_invalido"),
    ("TextoNumero(1,-1)", {}, "tipo_invalido"),
    ("TextoNumero(1,1.5)", {}, "tipo_invalido"),
    ("TextoNumero(1,16)", {}, "numero_invalido"),
    ("TextoNumero(Potencia(10,21),0)", {}, "numero_invalido"),
    ("TextoData('a')", {}, "tipo_invalido"),
    ("TextoData(0,'x')", {}, "tipo_invalido"),
    ("TextoData(0,1)", {}, "tipo_invalido"),
    ("TextoData(253402300800000)", {}, "numero_invalido"),
    ("TextoData(-62135596800001)", {}, "numero_invalido"),
]

# ataque de custo por passo: cada `Unicos` de 1.024 dicionários faz ~524 mil comparações estruturais;
# 40 termos somados são ~21 milhões — o orçamento de PASSOS é posto a 10^9 para que só o RELÓGIO corte
_ATAQUE_TEMPO = " + ".join(["Contagem(Unicos($x))"] * 40)
_CONTEXTO_ATAQUE = {"x": [{"a": i} for i in range(1024)]}
MARGEM_MS = 100  # limite 50 ms + folga para a máquina sob carga (o valor medido vai para tests/medidas)


@pytest.fixture(scope="module")
def erros_js():
    vetores = [{"entrada": e, "contexto": c} for e, c, _ in ERROS]
    r = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=json.dumps(vetores),
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    return json.loads(r.stdout)


@pytest.mark.parametrize("i,caso", list(enumerate(ERROS)), ids=[e for e, _, _ in ERROS])
def test_erro_nomeado_igual_nos_dois_runtimes(i, caso, erros_js):
    expressao, contexto, codigo = caso
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto(expressao, contexto)
    assert exc.value.codigo == codigo
    assert erros_js[i]["erro"] == codigo


def test_operacoes_nao_mutam_colecoes_do_chamador():
    contexto = {"x": [3, 1, 3, {"a": [4]}]}
    original = json.dumps(contexto)
    for texto in ["Reverter($x)", "Unicos($x)", "Obter($x,3)"]:
        avaliar_texto(texto, contexto)
        assert json.dumps(contexto) == original


def test_contexto_ciclico_rejeitado_com_erro_nomeado():
    ciclo = []
    ciclo.append(ciclo)
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto("$x", {"x": ciclo})
    assert exc.value.codigo in {"tipo_invalido", "valor_grande"}


def test_orcamento_conta_elementos_da_colecao():
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto("Soma($x)", {"x": [1] * 500}, limite_passos=100)
    assert exc.value.codigo == "limite_passos"


def test_tempo_zero_interrompe_avaliacao_curta():
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto("1", limite_ms=0)
    assert exc.value.codigo == "tempo_excedido"


def medir_corte_python_ms() -> tuple[str, float]:
    t0 = time.perf_counter()
    try:
        avaliar_texto(_ATAQUE_TEMPO, _CONTEXTO_ATAQUE, limite_passos=10**9, limite_ms=50)
    except ErroExpressao as exc:
        return exc.codigo, (time.perf_counter() - t0) * 1000.0
    raise AssertionError("o ataque terminou sem erro")  # pragma: no cover


def medir_corte_javascript_ms() -> tuple[str, float]:
    script = """
import { avaliarTexto, LIMITE_MS_CLIENTE } from './web/js/expressao/avaliador.js';
const ctx = JSON.parse(process.argv[1]);
const t0 = performance.now();
try { avaliarTexto(process.argv[2], ctx, {limitePassos: 1e9, limiteMs: LIMITE_MS_CLIENTE}); }
catch (e) { process.stdout.write(JSON.stringify({codigo: e.codigo, ms: performance.now() - t0})); process.exit(0); }
process.stdout.write(JSON.stringify({codigo: null, ms: performance.now() - t0}));
"""
    r = subprocess.run(
        ["node", "--input-type=module", "-e", script, json.dumps(_CONTEXTO_ATAQUE), _ATAQUE_TEMPO],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    dados = json.loads(r.stdout)
    return dados["codigo"], dados["ms"]


def test_ataque_de_custo_por_passo_e_cortado_pelo_relogio_em_50_ms_no_python():
    """Portão "laço infinito/recursão cortado em ≤ 50 ms com erro nomeado", agora com o custo escondido
    dentro de UMA chamada (comparação estrutural n² em `Unicos`), não só com árvore funda/larga."""
    codigo, ms = medir_corte_python_ms()
    assert codigo == "tempo_excedido"
    assert ms < 50 + MARGEM_MS, f"corte demorou {ms:.1f} ms"


def test_ataque_de_custo_por_passo_e_cortado_pelo_relogio_em_50_ms_no_javascript():
    codigo, ms = medir_corte_javascript_ms()
    assert codigo == "tempo_excedido"
    assert ms < 50 + MARGEM_MS, f"corte demorou {ms:.1f} ms"


def test_js_nao_executa_getters_nem_le_prototipo():
    script = """
import { avaliarTexto } from './web/js/expressao/avaliador.js';
let leituras = 0;
const contexto = {};
Object.defineProperty(contexto, 'x', {get() {leituras++; return 7;}});
const herdado = Object.create({x: 7});
const interno = {};
Object.defineProperty(interno, 'a', {enumerable: true, get() {leituras++; return 7;}});
const casos = [["$x",contexto],["$x",herdado],["Obter($x,'a')",{x:interno}]];
const resultados = casos.map(([texto,ctx]) => {
  try { return {valor:avaliarTexto(texto,ctx)}; }
  catch(e) { return {erro:e.codigo}; }
});
process.stdout.write(JSON.stringify({leituras,resultados}));
"""
    r = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    dados = json.loads(r.stdout)
    assert dados["leituras"] == 0
    assert all(x.get("erro") in {"campo_nao_permitido", "tipo_invalido"} for x in dados["resultados"])


# Portão "formatação de número e data em pt-BR conferida". O esperado abaixo é escrito à mão a partir
# da regra (milhar ".", decimal ",", 4 formatos de data, UTC), NÃO copiado da saída do avaliador; e é
# conferido nos DOIS runtimes, porque `Number.prototype.toFixed` e `str(float)` divergem por padrão.
PT_BR = [
    ("TextoNumero(1234.5)", "1.234,50"),
    ("TextoNumero(0)", "0,00"),
    ("TextoNumero(0, 0)", "0"),
    ("TextoNumero(-0.004, 2)", "0,00"),  # zero nunca leva sinal
    ("TextoNumero(-1234.567, 1)", "-1.234,6"),
    ("TextoNumero(2.5, 0)", "3"),  # empate para longe de zero, não banker's rounding
    ("TextoNumero(-2.5, 0)", "-3"),
    ("TextoNumero(1000000, 0)", "1.000.000"),
    ("TextoNumero(999.995, 2)", "1.000,00"),  # 999.995 em double é 999.995000000000004..., sobe
    ("TextoNumero(1.005, 2)", "1,00"),  # idem: 1.00499999...
    ("TextoNumero(123456789.987, 3)", "123.456.789,987"),
    ("TextoNumero(1, 15)", "1,000000000000000"),
    ("TextoData(0)", "01/01/1970"),
    ("TextoData(0, 'data_hora')", "01/01/1970 00:00"),
    ("TextoData(0, 'data_hora_segundos')", "01/01/1970 00:00:00"),
    ("TextoData(0, 'extenso')", "1 de janeiro de 1970"),
    ("TextoData(-1)", "31/12/1969"),  # antes da época, ainda UTC
    ("TextoData(1788652800000, 'extenso')", "6 de setembro de 2026"),
    ("TextoData(1740787199999, 'data_hora_segundos')", "28/02/2025 23:59:59"),
    ("TextoData(1709164800000, 'extenso')", "29 de fevereiro de 2024"),  # bissexto
    ("Concatenar('R$ ', TextoNumero(1234.5))", "R$ 1.234,50"),
]


@pytest.fixture(scope="module")
def pt_br_js():
    vetores = [{"entrada": e, "contexto": {}} for e, _ in PT_BR]
    r = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=json.dumps(vetores),
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    return json.loads(r.stdout)


@pytest.mark.parametrize("i,caso", list(enumerate(PT_BR)), ids=[e for e, _ in PT_BR])
def test_formatacao_pt_br_confere_nos_dois_runtimes(i, caso, pt_br_js):
    expressao, esperado = caso
    assert avaliar_texto(expressao, {}) == esperado
    assert pt_br_js[i]["erro"] is None, pt_br_js[i]
    assert pt_br_js[i]["resultado"] == esperado
