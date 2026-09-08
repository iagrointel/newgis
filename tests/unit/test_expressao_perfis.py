"""Perfis de uso da linguagem de expressão no navegador (item L5-11-expressoes-no-navegador).

Três coisas são provadas aqui, e as três são cláusulas do portão:
1. os mesmos vetores de perfil (`tests/expressoes/vetores_perfis.json`) dão o MESMO valor no
   avaliador Python e no avaliador JavaScript;
2. a MESMA expressão avaliada no perfil `popup` e no perfil `calculo_formulario` dá o mesmo valor,
   nos dois runtimes (quatro caminhos, um valor só);
3. expressão que não termina é cortada pelo orçamento do perfil, com erro nomeado, nos dois lados.

O isolamento (sem rede, sem outro inquilino) é provado por varredura: árvore sintática do módulo
Python e texto do módulo JavaScript."""

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.expressao.avaliador_py import ErroExpressao  # noqa: E402
from app.expressao.perfis import (  # noqa: E402
    CAMPOS_RESERVADOS,
    PERFIS,
    avaliar_perfil,
    contexto_da_feicao,
    tipo_do_valor,
)

RUNNER = RAIZ / "tests" / "expressoes" / "executar_js.mjs"
VETORES_PERFIS = RAIZ / "tests" / "expressoes" / "vetores_perfis.json"
MODULO_PERFIS_PY = RAIZ / "app" / "expressao" / "perfis.py"
MODULO_PERFIS_JS = RAIZ / "web" / "js" / "expressao" / "perfis.js"

VETORES = json.loads(VETORES_PERFIS.read_text(encoding="utf-8"))
# perfis que aceitam o mesmo conjunto de tipos: a mesma expressão tem de dar o mesmo valor nos dois
PAR_DO_PORTAO = ["popup", "calculo_formulario"]
_ATAQUE = " + ".join(["Contagem(Unicos($x))"] * 40)
_FEICAO_ATAQUE = {"atributos": {"x": [{"a": i} for i in range(1024)]}, "geometria": None}
MARGEM_MS = 100  # 50 ms do perfil + folga para a máquina sob carga (o valor medido vai para tests/medidas)


def _canonico(valor):
    return json.dumps(valor, sort_keys=True, ensure_ascii=False)


@pytest.fixture(scope="module")
def resultados_js():
    r = subprocess.run(
        ["node", str(RUNNER), "--perfis", "--stdin"],
        input=json.dumps(VETORES),
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def pares_js():
    casos = [dict(v, pares=PAR_DO_PORTAO) for v in VETORES if v["perfil"] == "popup"]
    r = subprocess.run(
        ["node", str(RUNNER), "--perfis-pares", "--stdin"],
        input=json.dumps(casos),
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    return casos, json.loads(r.stdout)


# ------------------------------------------------------------------ contrato dos perfis


def test_os_sete_perfis_da_hipotese_existem():
    assert set(PERFIS) == {
        "popup",
        "rotulo",
        "calculo_formulario",
        "visibilidade",
        "restricao",
        "indicador_painel",
        "titulo_dinamico",
    }


def test_perfis_do_javascript_sao_os_mesmos_do_python():
    r = subprocess.run(
        ["node", str(RUNNER), "--perfis", "--nomes-perfis"], capture_output=True, text=True, timeout=30, check=True
    )
    assert set(json.loads(r.stdout)) == set(PERFIS)


def test_todo_perfil_declara_tipos_orcamento_e_descricao():
    for nome, perfil in PERFIS.items():
        assert perfil["tipos"], nome
        assert set(perfil["tipos"]) <= {"texto", "numero", "booleano", "nulo"}, nome
        assert perfil["limite_ms"] in (50, 500), nome
        assert perfil["limite_passos"] > 0, nome
        assert perfil["descricao"].strip(), nome


def test_perfil_desconhecido_da_erro_nomeado():
    for nome in ("inexistente", "", 7, None):
        with pytest.raises(ErroExpressao) as excecao:
            avaliar_perfil(nome, "1")
        assert excecao.value.codigo == "perfil_desconhecido"


def test_tipo_do_valor_nomeia_lista_e_dicionario_sem_depender_da_lingua():
    assert tipo_do_valor(None) == "nulo"
    assert tipo_do_valor(True) == "booleano"
    assert tipo_do_valor(1) == "numero"
    assert tipo_do_valor(1.5) == "numero"
    assert tipo_do_valor("a") == "texto"
    assert tipo_do_valor([1]) == "lista"
    assert tipo_do_valor({"a": 1}) == "dicionario"


# ------------------------------------------------------------------ montagem do contexto


def test_contexto_so_tem_atributos_da_feicao_mais_os_dois_reservados():
    feicao = {"atributos": {"nome": "Gleba 1", "area_ha": 12.5}, "geometria": None}
    contexto = contexto_da_feicao(feicao)
    assert set(contexto) == {"nome", "area_ha", *CAMPOS_RESERVADOS}


def test_atributo_com_nome_que_nao_e_identificador_nao_vira_campo():
    feicao = {"atributos": {"nome do lote": "L-7", "área": 1, "a-b": 2, "3x": 3}, "geometria": None}
    contexto = contexto_da_feicao(feicao)
    assert set(contexto) == set(CAMPOS_RESERVADOS)
    assert avaliar_perfil("popup", "Atributo($feicao, 'nome do lote')", feicao) == "L-7"


def test_atributo_chamado_feicao_ou_geometria_nao_sombreia_o_reservado():
    feicao = {"atributos": {"feicao": "sombra", "geometria": "sombra"}, "geometria": None}
    contexto = contexto_da_feicao(feicao)
    assert contexto["feicao"]["atributos"]["feicao"] == "sombra"
    assert contexto["geometria"] is None


def test_feicao_ausente_ainda_produz_contexto_valido():
    contexto = contexto_da_feicao(None)
    assert set(contexto) == set(CAMPOS_RESERVADOS)
    assert avaliar_perfil("visibilidade", "EhNulo($geometria)", None) is True


@pytest.mark.parametrize(
    "feicao",
    [
        [1, 2],
        "texto",
        {"atributos": [1, 2], "geometria": None},
        {"atributos": {"a": 1}, "geometria": [1, 2]},
        {"atributos": {1: "chave nao textual"}, "geometria": None},
    ],
)
def test_feicao_fora_do_contrato_da_erro_nomeado(feicao):
    with pytest.raises(ErroExpressao) as excecao:
        avaliar_perfil("popup", "1", feicao)
    assert excecao.value.codigo == "feicao_invalida"


def test_expressao_nao_alcanca_campo_de_outra_feicao():
    """Isolamento: o contexto é montado da feição RECEBIDA e de mais nada. Avaliar contra a feição A
    e depois contra a B não deixa rastro de uma na outra (nada de estado compartilhado)."""
    a = {"atributos": {"segredo_a": "x"}, "geometria": None}
    b = {"atributos": {"publico_b": "y"}, "geometria": None}
    assert avaliar_perfil("popup", "$segredo_a", a) == "x"
    with pytest.raises(ErroExpressao) as excecao:
        avaliar_perfil("popup", "$segredo_a", b)
    assert excecao.value.codigo == "campo_nao_permitido"
    assert avaliar_perfil("popup", "$publico_b", b) == "y"


def test_contexto_nao_e_modificado_pela_avaliacao():
    feicao = {"atributos": {"lista": [1, 2, 3]}, "geometria": None}
    avaliar_perfil("popup", "Contagem(Reverter($lista))", feicao)
    assert feicao["atributos"]["lista"] == [1, 2, 3]


# ------------------------------------------------------------------ vetores nos dois runtimes


@pytest.mark.parametrize("i", range(len(VETORES)), ids=[v["descricao"] for v in VETORES])
def test_vetor_de_perfil_confere_no_python(i):
    vetor = VETORES[i]
    try:
        valor, codigo = avaliar_perfil(vetor["perfil"], vetor["entrada"], vetor.get("feicao")), None
    except ErroExpressao as excecao:
        valor, codigo = None, excecao.codigo
    assert codigo == vetor.get("erro"), vetor["descricao"]
    assert _canonico(valor) == _canonico(vetor.get("saida")), vetor["descricao"]


@pytest.mark.parametrize("i", range(len(VETORES)), ids=[v["descricao"] for v in VETORES])
def test_vetor_de_perfil_confere_no_javascript(i, resultados_js):
    vetor, obtido = VETORES[i], resultados_js[i]
    assert obtido["entrada"] == vetor["entrada"]
    assert obtido["erros"][0] == vetor.get("erro"), vetor["descricao"]
    assert _canonico(obtido["resultados"][0]) == _canonico(vetor.get("saida")), vetor["descricao"]


def test_ao_menos_cinquenta_vetores_de_perfil_cobrindo_os_sete_perfis():
    assert len(VETORES) >= 50
    assert {v["perfil"] for v in VETORES} == set(PERFIS)


# ------------------------------------------------------------------ cláusula do portão: popup == cálculo


def test_mesma_expressao_no_popup_e_no_calculo_de_formulario_da_o_mesmo_valor(pares_js):
    """Cláusula literal do portão. Quatro caminhos para cada expressão — popup e cálculo de
    formulário, no servidor (Python) e no navegador (JavaScript) — e um valor só."""
    casos, js = pares_js
    assert casos, "nenhum vetor de popup para o par do portão"
    for caso, obtido in zip(casos, js, strict=True):
        valores = []
        for perfil in PAR_DO_PORTAO:
            try:
                valores.append(("valor", _canonico(avaliar_perfil(perfil, caso["entrada"], caso.get("feicao")))))
            except ErroExpressao as excecao:
                valores.append(("erro", excecao.codigo))
        for resultado, erro in zip(obtido["resultados"], obtido["erros"], strict=True):
            valores.append(("erro", erro) if erro else ("valor", _canonico(resultado)))
        assert len(set(valores)) == 1, f"{caso['entrada']}: {valores}"


def test_o_par_do_portao_aceita_os_mesmos_tipos_de_retorno():
    """Se os dois perfis não aceitassem os mesmos tipos, a igualdade acima seria vazia de sentido."""
    assert set(PERFIS["popup"]["tipos"]) == set(PERFIS["calculo_formulario"]["tipos"])


def test_perfil_recusa_tipo_de_retorno_fora_do_contrato():
    feicao = {"atributos": {"n": 1, "t": "a", "b": True}, "geometria": None}
    recusas = [
        ("visibilidade", "$n"),
        ("visibilidade", "$t"),
        ("restricao", "$t"),
        ("indicador_painel", "$t"),
        ("indicador_painel", "$b"),
        ("rotulo", "$b"),
        ("titulo_dinamico", "$b"),
        ("popup", "Lista(1)"),
        ("calculo_formulario", "$feicao"),
    ]
    for perfil, expressao in recusas:
        with pytest.raises(ErroExpressao) as excecao:
            avaliar_perfil(perfil, expressao, feicao)
        assert excecao.value.codigo == "tipo_de_retorno_invalido", (perfil, expressao)


# ------------------------------------------------------------------ corte por tempo, nos dois lados


def medir_corte_do_perfil_python_ms() -> tuple[str, float]:
    t0 = time.perf_counter()
    try:
        avaliar_perfil("popup", _ATAQUE, _FEICAO_ATAQUE, limite_passos=10**9)
    except ErroExpressao as excecao:
        return excecao.codigo, (time.perf_counter() - t0) * 1000.0
    raise AssertionError("o ataque terminou sem erro")  # pragma: no cover


def medir_corte_do_perfil_javascript_ms() -> tuple[str, float]:
    script = """
import { avaliarPerfil } from './web/js/expressao/perfis.js';
const feicao = JSON.parse(process.argv[1]);
const t0 = performance.now();
try { avaliarPerfil('popup', process.argv[2], feicao, {limitePassos: 1e9}); }
catch (e) { process.stdout.write(JSON.stringify({codigo: e.codigo, ms: performance.now() - t0})); process.exit(0); }
process.stdout.write(JSON.stringify({codigo: null, ms: performance.now() - t0}));
"""
    r = subprocess.run(
        ["node", "--input-type=module", "-e", script, json.dumps(_FEICAO_ATAQUE), _ATAQUE],
        cwd=RAIZ,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    dados = json.loads(r.stdout)
    return dados["codigo"], dados["ms"]


def test_expressao_sem_fim_e_cortada_pelo_orcamento_do_perfil_no_python():
    codigo, ms = medir_corte_do_perfil_python_ms()
    assert codigo == "tempo_excedido"
    assert ms < PERFIS["popup"]["limite_ms"] + MARGEM_MS, f"corte demorou {ms:.1f} ms"


def test_expressao_sem_fim_e_cortada_pelo_orcamento_do_perfil_no_javascript():
    codigo, ms = medir_corte_do_perfil_javascript_ms()
    assert codigo == "tempo_excedido"
    assert ms < PERFIS["popup"]["limite_ms"] + MARGEM_MS, f"corte demorou {ms:.1f} ms"


def test_orcamento_de_passos_do_perfil_corta_quando_o_relogio_esta_folgado():
    with pytest.raises(ErroExpressao) as excecao:
        avaliar_perfil("popup", _ATAQUE, _FEICAO_ATAQUE, limite_ms=10**6)
    assert excecao.value.codigo == "limite_passos"


# ------------------------------------------------------------------ isolamento por varredura


def test_modulo_de_perfis_do_python_nao_tem_entrada_e_saida():
    arvore = ast.parse(MODULO_PERFIS_PY.read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add(no.module or "")
    assert importados <= {"typing", "app.expressao.avaliador_py"}, importados
    proibidos = {"eval", "exec", "compile", "open", "__import__", "getattr", "setattr", "input"}
    chamados = {
        no.func.id for no in ast.walk(arvore) if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert not (chamados & proibidos), chamados & proibidos


def test_modulo_de_perfis_do_javascript_nao_toca_rede_nem_janela():
    # varre o CÓDIGO, não a prosa: as linhas de comentário citam os nomes proibidos de propósito
    texto = "\n".join(
        linha for linha in MODULO_PERFIS_JS.read_text(encoding="utf-8").splitlines()
        if not linha.lstrip().startswith("//")
    )
    for proibido in (
        "fetch",
        "XMLHttpRequest",
        "WebSocket",
        "navigator",
        "localStorage",
        "document",
        "eval(",
        "new Function",
        "import(",
        "require(",
        "process.",
        "window",
    ):
        assert proibido not in texto, proibido
