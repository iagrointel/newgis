"""Funções de rede na linguagem de expressão (item L4-29-regras-de-atributo-de-rede): as seis
funções (`Subrede`, `Alimentador`, `TensaoAlimentador`, `ContarJusante`, `NivelRede`,
`AtributoRede`) leem a chave reservada `rede` do contexto e existem nos DOIS avaliadores com o
mesmo contrato. Casos de valor vão para `tests/expressoes/vetores_convergencia.json` (prova de
concordância byte a byte); aqui ficam os casos de ERRO nomeado e os de contrato (`rede` fora do
contexto é permissão, ausente dentro de `rede` é nulo)."""

import json
import subprocess
from pathlib import Path

import pytest

from app.expressao.avaliador_py import TABELA_FUNCOES, ErroExpressao, avaliar_texto

ROOT = Path(__file__).resolve().parents[2]
RUNNER_JS = ROOT / "tests" / "expressoes" / "executar_js.mjs"

FUNCOES_REDE = ("Subrede", "Alimentador", "TensaoAlimentador", "ContarJusante", "NivelRede", "AtributoRede")

# (entrada, contexto, código de erro esperado) — conferido nos DOIS runtimes
ERROS = [
    ("Subrede()", {}, "campo_nao_permitido"),                      # sem contexto de rede: permissão
    ("AtributoRede('x')", {}, "campo_nao_permitido"),
    ("Subrede()", {"rede": None}, "tipo_invalido"),                # rede não-dicionário
    ("Subrede()", {"rede": "SR-CENTRO"}, "tipo_invalido"),
    ("Subrede()", {"rede": [1]}, "tipo_invalido"),
    ("AtributoRede(1)", {"rede": {"atributos": {}}}, "tipo_invalido"),
    ("AtributoRede(verdadeiro)", {"rede": {"atributos": {}}}, "tipo_invalido"),
    ("AtributoRede('__proto__')", {"rede": {"atributos": {}}}, "campo_nao_permitido"),
    ("AtributoRede('prototype')", {"rede": {"atributos": {}}}, "campo_nao_permitido"),
    ("AtributoRede('constructor')", {"rede": {"atributos": {}}}, "campo_nao_permitido"),
    ("AtributoRede('x')", {"rede": {"atributos": []}}, "tipo_invalido"),
    ("Subrede(1)", {"rede": {}}, "aridade_invalida"),
    ("AtributoRede()", {"rede": {}}, "aridade_invalida"),
    ("ContarJusante(1)", {"rede": {"jusante": 1}}, "aridade_invalida"),
]
CASOS_ERRO = [(e, c, cod) for e, c, cod in ERROS if cod != "ok"]


def test_as_seis_funcoes_de_rede_estao_na_tabela_dos_dois_avaliadores():
    for nome in FUNCOES_REDE:
        assert nome in TABELA_FUNCOES, nome
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--nomes-funcoes"], capture_output=True, text=True, timeout=15, check=True
    )
    assert set(FUNCOES_REDE) <= set(json.loads(r.stdout))


@pytest.mark.parametrize("entrada,contexto,codigo", CASOS_ERRO, ids=[e for e, _c, _c2 in CASOS_ERRO])
def test_erro_nomeado_no_python(entrada, contexto, codigo):
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto(entrada, contexto)
    assert exc.value.codigo == codigo


@pytest.mark.parametrize("entrada,contexto,codigo", CASOS_ERRO, ids=[e for e, _c, _c2 in CASOS_ERRO])
def test_erro_nomeado_no_javascript(entrada, contexto, codigo):
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--stdin"],
        input=json.dumps([{"entrada": entrada, "contexto": contexto}], ensure_ascii=True),
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    item = json.loads(r.stdout)[0]
    assert item["erro"] == codigo, item


def test_chave_ausente_dentro_de_rede_e_nulo_nunca_erro():
    """Contrato declarado em docs/EXPRESSAO.md §5 (Rede): objeto fora de subrede, jusante não
    calculada e atributo que o objeto não têm são NULO — a ausência é dado, não permissão."""
    contexto = {"rede": {"atributos": {"outra": 1}}}
    assert avaliar_texto("Subrede()", contexto) is None
    assert avaliar_texto("Alimentador()", contexto) is None
    assert avaliar_texto("TensaoAlimentador()", contexto) is None
    assert avaliar_texto("ContarJusante()", contexto) is None
    assert avaliar_texto("NivelRede()", contexto) is None
    assert avaliar_texto("AtributoRede('tensao_kv')", contexto) is None


def test_atributo_presente_com_valor_nulo_continua_nulo():
    assert avaliar_texto("AtributoRede('x')", {"rede": {"atributos": {"x": None}}}) is None


def test_rede_reservada_no_contexto_sobrepoe_atributo_de_mesmo_nome():
    """O motor achata os atributos do objeto no topo do contexto; a chave `rede` é reservada e
    sempre vence — um atributo de rede chamado `rede` nunca substitui o dicionário de rede."""
    contexto = {"tensao_kv": 13.8, "rede": {"atributos": {"tensao_kv": 13.8}}}
    assert avaliar_texto("AtributoRede('tensao_kv')", contexto) == 13.8


def test_rede_e_dicionario_do_contexto_como_outro_qualquer():
    """`rede` é uma chave do contexto como outra qualquer para o `$campo` — a reserva vale para as
    funções; `$rede` devolve o dicionário inteiro e a gramática não ganhou acesso aninhado novo
    (`$rede.nivel` é sintaxe inválida, como sempre foi para qualquer dicionário do contexto)."""
    contexto = {"rede": {"nivel": "mt"}}
    assert avaliar_texto("$rede", contexto) == {"nivel": "mt"}
    with pytest.raises(ErroExpressao) as exc:
        avaliar_texto("$rede.nivel", contexto)
    assert exc.value.codigo == "caractere_invalido"  # '.' não é gramática: nenhum acesso aninhado
