"""Coluna de rótulo pré-calculada no servidor (item L2-02-d-rotulos), para quando a expressão da
classe não compila para MapLibre (`app/expressao/compilador_maplibre.NaoCompilavel`).

O contrato completo (função de tile do Martin calculando a coluna em SQL, dentro do pipeline de
ingestão do L2-04) é trabalho de item irmão — ver `docs/PARIDADE.md` e o handoff deste item. Esta
passagem prova o que depende só da linguagem de expressão: (1) um nome de coluna determinístico e
estável para a mesma expressão; (2) o cálculo do valor por feição usando o MESMO avaliador Python
que o servidor de verdade vai chamar (`app/expressao/avaliador_py.avaliar_texto`); (3) a conversão
para texto NUNCA produz `'null'`/`'NaN'`/`'undefined'` — erro de avaliação (divisão por zero, campo
ausente, etc.) em uma feição vira rótulo vazio para aquela feição, e não derruba o lote inteiro
(refutação do item)."""

from __future__ import annotations

import hashlib

from app.expressao.avaliador_py import ErroExpressao, _formatar_numero, avaliar_texto

PREFIXO_COLUNA = "plat_rotulo_"
_TEXTOS_PROIBIDOS = {"null", "nan", "undefined", "none"}


def nome_coluna_servidor(expressao: str) -> str:
    """Nome determinístico e estável: mesma expressão → mesmo nome, em qualquer instalação (o hash
    não depende de ordem de inserção nem de id de banco, só do texto normalizado da expressão)."""
    digerido = hashlib.sha256(expressao.strip().encode("utf-8")).hexdigest()[:16]
    return f"{PREFIXO_COLUNA}{digerido}"


def texto_seguro(valor: object) -> str:
    """Canonicaliza o resultado do avaliador em texto de rótulo. Nunca devolve uma das grafias
    proibidas (comparação sem diferenciar caixa, cobre `Null`/`NULL` etc. também)."""
    if valor is None:
        texto = ""
    elif isinstance(valor, bool):
        texto = "verdadeiro" if valor else "falso"
    elif isinstance(valor, (int, float)):
        texto = _formatar_numero(float(valor))
    else:
        texto = str(valor)
    if texto.strip().lower() in _TEXTOS_PROIBIDOS:
        return ""
    return texto


def pre_calcular(expressao: str, feicoes: list[dict]) -> list[str]:
    """Uma string de rótulo por feição (mesma ordem). Uma feição cuja avaliação falha (campo
    ausente, divisão por zero, tipo incompatível) recebe rótulo vazio — o erro fica só nela, nunca
    propaga para as demais (é exatamente o que a refutação do item cobra)."""
    saida: list[str] = []
    for props in feicoes:
        try:
            valor = avaliar_texto(expressao, props)
        except ErroExpressao:
            saida.append("")
            continue
        saida.append(texto_seguro(valor))
    return saida
