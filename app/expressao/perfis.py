"""Perfis de uso da linguagem de expressão (item L5-11-expressoes-no-navegador).

Um PERFIL diz três coisas sobre uma expressão: onde ela é usada, que tipo de valor ela tem de
devolver e com que orçamento ela roda. O perfil NÃO muda a semântica da linguagem — a mesma
expressão avaliada em dois perfis que aceitam o mesmo tipo devolve o MESMO valor, e é essa
igualdade que o portão deste item exige entre o popup e o cálculo de formulário.

O contexto de avaliação é montado AQUI, a partir da feição que o chamador passa, e só dela: cada
atributo cujo nome é um identificador válido vira `$nome`, mais `$feicao` (a feição inteira, para
`Atributo`/`Geometria`) e `$geometria`. Não há acesso a rede, a banco, a arquivo nem a outra
feição — o módulo não importa nada além do avaliador, e `tests/unit/test_expressao_perfis.py`
prova isso varrendo a árvore sintática do próprio arquivo. Atributo com nome fora do vocabulário
de identificador (espaço, acento, hífen) não vira `$nome`; alcança-se por
`Atributo($feicao, 'nome com espaço')`.

Espelho exato em `web/js/expressao/perfis.js` (mesmos nomes de perfil, mesmos tipos aceitos,
mesmos orçamentos, mesmos códigos de erro).
"""

from typing import Any

from app.expressao.avaliador_py import (
    IDENT_RE,
    LIMITE_MS_SERVIDOR,
    MAX_PASSOS_PADRAO,
    ErroExpressao,
    analisar,
    avaliar,
)

LIMITE_MS_CLIENTE = 50  # o mesmo valor de LIMITE_MS_CLIENTE em web/js/expressao/avaliador.js

# Nomes que a montagem do contexto reserva: um atributo com esse nome NÃO vira `$nome` (só é
# alcançável por `Atributo($feicao, ...)`), para `$feicao`/`$geometria` significarem sempre a mesma
# coisa em toda expressão, venha a feição de onde vier.
CAMPOS_RESERVADOS = ("feicao", "geometria")

_ESCALAR = ("texto", "numero", "booleano", "nulo")

# nome do perfil → (tipos de retorno aceitos, orçamento de tempo em ms, orçamento de passos, onde roda)
PERFIS: dict[str, dict[str, Any]] = {
    "popup": {
        "tipos": _ESCALAR,
        "limite_ms": LIMITE_MS_CLIENTE,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "linha de conteúdo da janela de feição, avaliada no navegador a cada clique",
    },
    "rotulo": {
        "tipos": ("texto", "numero", "nulo"),
        "limite_ms": LIMITE_MS_CLIENTE,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "texto desenhado sobre a feição no mapa, avaliado no navegador a cada quadro",
    },
    "calculo_formulario": {
        "tipos": _ESCALAR,
        "limite_ms": LIMITE_MS_SERVIDOR,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "valor calculado de um campo do formulário de edição, conferido também no servidor",
    },
    "visibilidade": {
        "tipos": ("booleano", "nulo"),
        "limite_ms": LIMITE_MS_CLIENTE,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "mostra ou esconde um campo/elemento; nulo é 'não sei' e o chamador trata como escondido",
    },
    "restricao": {
        "tipos": ("booleano", "nulo"),
        "limite_ms": LIMITE_MS_SERVIDOR,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "verdadeiro = a feição pode ser gravada; falso ou nulo = a gravação é recusada",
    },
    "indicador_painel": {
        "tipos": ("numero", "nulo"),
        "limite_ms": LIMITE_MS_SERVIDOR,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "número exibido num indicador de painel",
    },
    "titulo_dinamico": {
        "tipos": ("texto", "numero", "nulo"),
        "limite_ms": LIMITE_MS_CLIENTE,
        "limite_passos": MAX_PASSOS_PADRAO,
        "descricao": "título de janela, aba ou painel montado a partir da feição",
    },
}


def tipo_do_valor(valor: Any) -> str:
    """Nome do tipo COMPARTILHADO entre os dois avaliadores (o `type().__name__` do Python e o
    `typeof` do JavaScript divergiriam em lista e dicionário)."""
    if valor is None:
        return "nulo"
    if type(valor) is bool:
        return "booleano"
    if type(valor) in (int, float):
        return "numero"
    if type(valor) is str:
        return "texto"
    if type(valor) is list:
        return "lista"
    if type(valor) is dict:
        return "dicionario"
    return "desconhecido"


def descricao_do_perfil(nome: str) -> dict[str, Any]:
    if type(nome) is not str or nome not in PERFIS:
        raise ErroExpressao("perfil_desconhecido", f"perfil desconhecido: {nome}", {"perfil": nome})
    return PERFIS[nome]


def _feicao_normalizada(feicao: Any) -> dict[str, Any]:
    if feicao is None:
        return {"atributos": {}, "geometria": None}
    if type(feicao) is not dict:
        raise ErroExpressao("feicao_invalida", "feição tem de ser um dicionário", {})
    atributos = feicao.get("atributos", {})
    if atributos is None:
        atributos = {}
    if type(atributos) is not dict or any(type(k) is not str for k in atributos):
        raise ErroExpressao("feicao_invalida", "atributos da feição têm de ser um dicionário de nomes", {})
    geometria = feicao.get("geometria")
    if geometria is not None and type(geometria) is not dict:
        raise ErroExpressao("feicao_invalida", "geometria da feição tem de ser um dicionário GeoJSON", {})
    return {"atributos": dict(atributos), "geometria": geometria}


def contexto_da_feicao(feicao: Any) -> dict[str, Any]:
    """Lista BRANCA de campos visíveis à expressão. Nada aqui vem de fora da feição recebida."""
    normalizada = _feicao_normalizada(feicao)
    contexto: dict[str, Any] = {}
    for nome, valor in normalizada["atributos"].items():
        if nome in CAMPOS_RESERVADOS or not IDENT_RE.match(nome):
            continue  # alcançável só por Atributo($feicao, '<nome>')
        contexto[nome] = valor
    contexto["feicao"] = normalizada
    contexto["geometria"] = normalizada["geometria"]
    return contexto


def avaliar_perfil(
    perfil: str,
    expressao: str,
    feicao: Any = None,
    *,
    limite_passos: int | None = None,
    limite_ms: float | None = None,
) -> Any:
    """Avalia `expressao` no `perfil` contra `feicao` e confere o TIPO de retorno do perfil."""
    descricao = descricao_do_perfil(perfil)
    valor = avaliar(
        analisar(expressao),
        contexto_da_feicao(feicao),
        limite_passos=descricao["limite_passos"] if limite_passos is None else limite_passos,
        limite_ms=descricao["limite_ms"] if limite_ms is None else limite_ms,
    )
    tipo = tipo_do_valor(valor)
    if tipo not in descricao["tipos"]:
        raise ErroExpressao(
            "tipo_de_retorno_invalido",
            f"perfil {perfil} espera {'/'.join(descricao['tipos'])}, a expressão devolveu {tipo}",
            {"perfil": perfil, "tipo": tipo},
        )
    return valor
