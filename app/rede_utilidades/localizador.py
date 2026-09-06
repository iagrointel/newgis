"""Linha de um caminho JSON dentro do texto ENVIADO pelo cliente.

Motivo: uma mensagem de erro que diz apenas `tipos[41].grupo` obriga quem enviou o pacote a contar elementos à
mão. Aqui o texto bruto é percorrido com o próprio decodificador do Python (`raw_decode` pula um valor inteiro
sem interpretá-lo), guardando o índice do caractere onde o caminho cai; a linha é a contagem de quebras até
esse índice. Não reformata nem reordena nada: a linha é a do arquivo que a pessoa mandou, do jeito que mandou.

Devolve `None` quando o caminho não existe no texto (por exemplo, erro de chave ausente): quem chama trata a
ausência de linha, nunca inventa uma."""

import json

_DEC = json.JSONDecoder()
_BRANCO = " \t\n\r"


def _pular_branco(texto: str, i: int) -> int:
    while i < len(texto) and texto[i] in _BRANCO:
        i += 1
    return i


def _indice(texto: str, caminho: list) -> int | None:
    i = _pular_branco(texto, 0)
    for passo in caminho:
        if i >= len(texto):
            return None
        if isinstance(passo, int):
            if texto[i] != "[":
                return None
            i = _pular_branco(texto, i + 1)
            posicao = 0
            while True:
                if i >= len(texto) or texto[i] == "]":
                    return None
                if posicao == passo:
                    break
                _, i = _DEC.raw_decode(texto, i)
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
                    posicao += 1
                    continue
                return None
        else:
            if texto[i] != "{":
                return None
            i = _pular_branco(texto, i + 1)
            achou = False
            while i < len(texto) and texto[i] != "}":
                chave, i = _DEC.raw_decode(texto, i)
                i = _pular_branco(texto, i)
                if i >= len(texto) or texto[i] != ":":
                    return None
                i = _pular_branco(texto, i + 1)
                if chave == passo:
                    achou = True
                    break
                _, i = _DEC.raw_decode(texto, i)
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
            if not achou:
                return None
    return i


def linha(texto: str, caminho: list) -> int | None:
    """Linha (a primeira é 1) onde o valor de `caminho` começa no texto bruto; None se o caminho não existe."""
    try:
        i = _indice(texto, list(caminho))
    except (ValueError, IndexError):
        return None
    return None if i is None else texto.count("\n", 0, i) + 1


def texto_do_caminho(caminho: list) -> str:
    """`['tipos', 3, 'grupo']` -> `tipos[3].grupo` (o que aparece na mensagem de erro)."""
    saida = ""
    for passo in caminho:
        saida += f"[{passo}]" if isinstance(passo, int) else (f".{passo}" if saida else str(passo))
    return saida or "(raiz)"
