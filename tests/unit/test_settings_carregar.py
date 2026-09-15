"""Teste de fiação de `app.settings.carregar()`: para cada campo string de `Settings`, um valor
sintético em `valores` tem de chegar, sem se perder, à Settings efetiva.

Nasceu do achado do item L7-19-segredos/L7-31 (conserto 15/09): a união de 10/09 acrescentou 25 campos
ao dataclass `Settings` (linhas ~127-151 de app/settings.py) e `carregar()` nunca leu 16 deles de
`valores` — inclusive `PLAT_GARAGE_CHAVE_ID`/`PLAT_GARAGE_CHAVE_SEGREDO`, a chave S3 própria da
homologação. Sem essa chave, `tests/unit/test_isolamento_homologacao.py::
test_configuracao_efetiva_de_homologacao_nao_tem_administracao` falhava: a configuração EFETIVA nunca
tinha a chave, e homologação continuava dependendo do token de administração. Este teste não sabe nada
de `PLAT_GARAGE_CHAVE_*` especificamente — ele itera `dataclasses.fields(Settings)` e cobra que
`carregar()` tenha lido cada campo string de algum lugar, para que o mesmo esquecimento não passe
despercebido da próxima vez que um campo novo entrar no dataclass.

Dois grupos ficam de fora do valor genérico "x":

- NAO_STRING: campos int/bool (PLAT_WORKER_PROCESSOS, PLAT_SMTP_TLS, PLAT_RENDER_*, ...) — "x" não é um
  inteiro nem um booleano válido. Testar cada um exigiria um valor por campo (o padrão/mínimo já é
  coberto por outros testes onde existe); o item pediu para SÓ LISTAR o que for ambíguo, não consertar
  às cegas — fica listado aqui, não testado por este arquivo.
- FORMATADOS: campos string com validação ou transformação própria (PLAT_DSN, PLAT_SECRET,
  PLAT_SECRET_ANTERIOR, PLAT_AMBIENTE, PLAT_URL_PUBLICA, PLAT_LOG_NIVEL, PLAT_DSN_WORKER) — "x" sozinho
  é um valor inválido para eles (não começa com postgresql://, não é hex64, não é ambiente conhecido,
  não começa com https://, não é nível de log, não tem o prefixo do papel do worker); usá-lo aqui daria
  falso-negativo, não cobertura real. Já têm teste dedicado em test_settings.py.

Conserto 15/09 (item de wt/segur): dos campos de NAO_STRING, os 9 abaixo — `PLAT_RENDER_POOL_TAMANHO`,
`PLAT_RENDER_FILA_MAX`, `PLAT_RENDER_TIMEOUT_S`, `PLAT_RENDER_TOKEN_TTL_S`, `PLAT_RENDER_MAX_PX`,
`PLAT_RENDER_MEMORIA_MB`, `PLAT_RENDER_IGNORAR_HTTPS`, `PLAT_SSE_LIGADO`, `PLAT_API_PROCESSOS` — eram o
resto do mesmo esquecimento (`carregar()` nunca os lia de `valores`, sempre o default do dataclass) e
ganharam padrão/mínimo em MANUAL.md §12.1. `INTEIROS_NOVOS`/`BOOLEANOS_NOVOS` abaixo testam, para cada um
deles: texto válido chega convertido (não como string) e texto inválido levanta `ErroConfiguracao`
nomeando a variável — a mesma cobertura que `test_settings.py` já dá aos formatados.
"""

import dataclasses

import pytest

from app.settings import ErroConfiguracao, Settings, carregar

BASE = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
    "PLAT_SECRET": "ab" * 32,
    "PLAT_AMBIENTE": "producao",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido/",
}

NAO_STRING = {
    "PLAT_WORKER_PROCESSOS",
    "PLAT_WORKER_MEMORIA_MB",
    "PLAT_JOB_MAX_REINICIOS",
    "PLAT_ROTA_MATRIZ_MAX",
    "PLAT_ROTA_ISOCRONA_MAX_PONTOS",
    "PLAT_SMTP_PORTA",
    "PLAT_SMTP_TLS",
    "PLAT_POOL_MIN",
    "PLAT_POOL_MAX",
    "PLAT_RENDER_POOL_TAMANHO",
    "PLAT_RENDER_FILA_MAX",
    "PLAT_RENDER_TIMEOUT_S",
    "PLAT_RENDER_TOKEN_TTL_S",
    "PLAT_RENDER_MAX_PX",
    "PLAT_RENDER_MEMORIA_MB",
    "PLAT_RENDER_IGNORAR_HTTPS",
    "PLAT_SSE_LIGADO",
    "PLAT_API_PROCESSOS",
}

FORMATADOS = {
    "PLAT_DSN",
    "PLAT_SECRET",
    "PLAT_SECRET_ANTERIOR",
    "PLAT_AMBIENTE",
    "PLAT_URL_PUBLICA",
    "PLAT_LOG_NIVEL",
    "PLAT_DSN_WORKER",
}

TODOS_OS_CAMPOS = {f.name for f in dataclasses.fields(Settings)}
CAMPOS_STRING = sorted(TODOS_OS_CAMPOS - NAO_STRING - FORMATADOS)


def _e_tipo_string(tipo) -> bool:
    if tipo is str:
        return True
    args = getattr(tipo, "__args__", None)
    return bool(args) and set(args) == {str, type(None)}


def test_nao_string_esta_com_o_tipo_certo():
    """Trava de digitação: se um nome sair de NAO_STRING/FORMATADOS por engano, ou um campo novo for
    classificado errado, este teste falha em vez de o campo escapar silenciosamente da cobertura."""
    tipos = {f.name: f.type for f in dataclasses.fields(Settings)}
    for campo in NAO_STRING:
        assert campo in tipos, f"{campo} não existe mais em Settings"
        assert tipos[campo] in (int, bool), f"{campo} está em NAO_STRING mas o tipo é {tipos[campo]}"
    for campo in FORMATADOS | set(CAMPOS_STRING):
        assert _e_tipo_string(tipos[campo]), f"{campo} não é string mas não está em NAO_STRING"


@pytest.mark.parametrize("campo", CAMPOS_STRING)
def test_campo_string_chega_a_settings_efetiva(campo):
    valores = {**BASE, campo: "x"}
    efetiva = carregar(valores)
    assert getattr(efetiva, campo) == "x", (
        f"{campo} não chegou à Settings efetiva sem alteração — carregar() provavelmente não lê este "
        f"campo de `valores` (o mesmo esquecimento do achado PLAT_GARAGE_CHAVE_ID/PLAT_GARAGE_CHAVE_SEGREDO)"
    )


# --- conserto 15/09: os 9 campos int/bool que ficaram de fora do primeiro conserto (docstring do módulo).
# Ambos os conjuntos usam a MESMA função de conversão que o resto do módulo já usa (_inteiro/_booleano) —
# este teste não sabe disso, só observa o comportamento pela API pública `carregar()`.

INTEIROS_NOVOS = sorted(
    {
        "PLAT_RENDER_POOL_TAMANHO",
        "PLAT_RENDER_FILA_MAX",
        "PLAT_RENDER_TIMEOUT_S",
        "PLAT_RENDER_TOKEN_TTL_S",
        "PLAT_RENDER_MAX_PX",
        "PLAT_RENDER_MEMORIA_MB",
        "PLAT_API_PROCESSOS",
    }
)

BOOLEANOS_NOVOS = sorted({"PLAT_RENDER_IGNORAR_HTTPS", "PLAT_SSE_LIGADO"})


def test_inteiros_e_booleanos_novos_batem_com_nao_string():
    """Trava de digitação: os dois conjuntos acima têm de ser exatamente os 9 campos que a docstring do
    módulo promete testar — nem a mais (campo que não existe mais), nem a menos (campo esquecido de novo)."""
    assert set(INTEIROS_NOVOS) | set(BOOLEANOS_NOVOS) == {
        "PLAT_RENDER_POOL_TAMANHO",
        "PLAT_RENDER_FILA_MAX",
        "PLAT_RENDER_TIMEOUT_S",
        "PLAT_RENDER_TOKEN_TTL_S",
        "PLAT_RENDER_MAX_PX",
        "PLAT_RENDER_MEMORIA_MB",
        "PLAT_RENDER_IGNORAR_HTTPS",
        "PLAT_SSE_LIGADO",
        "PLAT_API_PROCESSOS",
    }


@pytest.mark.parametrize("campo", INTEIROS_NOVOS)
def test_campo_inteiro_texto_valido_converte(campo):
    efetiva = carregar({**BASE, campo: "7"})
    valor = getattr(efetiva, campo)
    assert valor == 7 and isinstance(valor, int), f"{campo} não converteu '7' para o inteiro 7"


@pytest.mark.parametrize("campo", INTEIROS_NOVOS)
def test_campo_inteiro_texto_invalido_da_erro_com_o_nome_da_variavel(campo):
    with pytest.raises(ErroConfiguracao, match=campo):
        carregar({**BASE, campo: "abacate"})


@pytest.mark.parametrize("campo", INTEIROS_NOVOS)
def test_campo_inteiro_abaixo_do_minimo_da_erro_com_o_nome_da_variavel(campo):
    """Mínimo registrado em MANUAL.md §12.1: inteiro >= 1 (regra geral de são; nenhum dos 9 tinha mínimo
    documentado antes deste conserto)."""
    with pytest.raises(ErroConfiguracao, match=campo):
        carregar({**BASE, campo: "0"})


@pytest.mark.parametrize(
    "campo,texto,esperado",
    [
        (campo, texto, esperado)
        for campo in BOOLEANOS_NOVOS
        for texto, esperado in [
            ("1", True),
            ("true", True),
            ("verdadeiro", True),
            ("sim", True),
            ("0", False),
            ("false", False),
            ("falso", False),
            ("nao", False),
            ("não", False),
        ]
    ],
)
def test_campo_booleano_texto_valido_converte(campo, texto, esperado):
    efetiva = carregar({**BASE, campo: texto})
    valor = getattr(efetiva, campo)
    assert valor is esperado, f"{campo}={texto!r} deveria converter para {esperado}, veio {valor!r}"


@pytest.mark.parametrize("campo", BOOLEANOS_NOVOS)
def test_campo_booleano_texto_invalido_da_erro_com_o_nome_da_variavel(campo):
    with pytest.raises(ErroConfiguracao, match=campo):
        carregar({**BASE, campo: "talvez"})
