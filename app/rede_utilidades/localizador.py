"""Linha de um caminho JSON dentro do texto ENVIADO pelo cliente.

Motivo: uma mensagem de erro que diz apenas `tipos[41].grupo` obriga quem enviou o pacote a contar elementos à
mão. Aqui o texto bruto é percorrido com o próprio decodificador do Python (`raw_decode` pula um valor inteiro
sem interpretá-lo); a LINHA é a contagem de quebras até esse índice. Não reformata nem reordena nada: a linha é
a do arquivo que a pessoa mandou, do jeito que mandou.

Devolve `None` quando o caminho não existe no texto (por exemplo, erro de chave ausente): quem chama trata a
ausência de linha, nunca inventa uma.

MAPA, não busca do zero. `_indice` original refazia o percurso do início do texto A CADA CHAMADA — para um
pacote com milhares de problemas (a maioria em `tipos[N]`), isso é quadrático: localizar `tipos[3999]` decodifica
os 3999 itens anteriores de novo, e de novo para `tipos[3998]`, etc (achado A4, `L4-01-a-pacote-de-ativos`,
turno 3). Aqui o texto é percorrido UMA VEZ, construindo uma árvore-espelho com o deslocamento (offset) de cada
nó; a busca por caminho depois é só uma travessia da árvore, em profundidade, não do texto. Uma chave repetida
no MESMO objeto sobrescreve o offset anterior ao construir o mapa — a mesma semântica de `json.loads`, então o
caminho aponta sempre para a ocorrência que a validação de fato usou (achado A2b), sem lógica à parte.

O mapa é guardado por IDENTIDADE do objeto `str` (não por conteúdo — comparar/hashear string de megabytes a
cada chamada custaria o mesmo que refazer o percurso). Dentro de UMA leitura de pacote o texto é sempre o mesmo
objeto, então o cache atende todas as chamadas de `linha()` com um único percurso."""

import json

_DEC = json.JSONDecoder()
_BRANCO = " \t\n\r"
_CACHE_TAMANHO_MAX = 1  # só um pacote é validado por vez neste processo


def _pular_branco(texto: str, i: int) -> int:
    while i < len(texto) and texto[i] in _BRANCO:
        i += 1
    return i


def _construir_mapa(texto: str) -> tuple:
    """Uma passada pelo texto inteiro. Devolve o nó-raiz: `{"offset": int}`, com `"chaves"` se for objeto
    (código -> sub-nó) e `"itens"` se for lista (sub-nó por posição)."""

    def andar(i: int):
        i = _pular_branco(texto, i)
        inicio = i
        if i < len(texto) and texto[i] == "{":
            i = _pular_branco(texto, i + 1)
            chaves: dict = {}
            while i < len(texto) and texto[i] != "}":
                chave, i = _DEC.raw_decode(texto, i)
                i = _pular_branco(texto, i)
                if i >= len(texto) or texto[i] != ":":
                    break
                i = _pular_branco(texto, i + 1)
                sub, i = andar(i)
                chaves[chave] = sub  # sobrescreve: última ocorrência vence, como json.loads
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
            if i < len(texto) and texto[i] == "}":
                i += 1
            return {"offset": inicio, "chaves": chaves}, i
        if i < len(texto) and texto[i] == "[":
            i = _pular_branco(texto, i + 1)
            itens: list = []
            while i < len(texto) and texto[i] != "]":
                sub, i = andar(i)
                itens.append(sub)
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
            if i < len(texto) and texto[i] == "]":
                i += 1
            return {"offset": inicio, "itens": itens}, i
        _, i = _DEC.raw_decode(texto, i)
        return {"offset": inicio}, i

    raiz, _ = andar(0)
    return raiz


_cache: dict[int, tuple[str, dict]] = {}


def _mapa(texto: str) -> dict | None:
    chave = id(texto)
    entrada = _cache.get(chave)
    if entrada is not None and entrada[0] is texto:
        return entrada[1]
    try:
        mapa = _construir_mapa(texto)
    except (ValueError, IndexError):
        return None
    if len(_cache) >= _CACHE_TAMANHO_MAX:
        _cache.clear()
    _cache[chave] = (texto, mapa)
    return mapa


def linha(texto: str, caminho: list) -> int | None:
    """Linha (a primeira é 1) onde o valor de `caminho` começa no texto bruto; None se o caminho não existe."""
    no = _mapa(texto)
    for passo in caminho:
        if no is None:
            return None
        if isinstance(passo, int):
            itens = no.get("itens")
            if itens is None or not (0 <= passo < len(itens)):
                return None
            no = itens[passo]
        else:
            chaves = no.get("chaves")
            if chaves is None or passo not in chaves:
                return None
            no = chaves[passo]
    return None if no is None else texto.count("\n", 0, no["offset"]) + 1


def chaves_repetidas(texto: str) -> list[dict]:
    """Toda chave que aparece mais de uma vez dentro do MESMO objeto, em qualquer profundidade — inclusive uma
    seção inteira repetida no topo do pacote (`"tiers"` duas vezes) ou um campo repetido dentro de um item
    (`{"codigo": "a", "codigo": "b"}`). `json.loads` fica com a ÚLTIMA ocorrência sem avisar (achado A2); aqui
    cada duplicata sai com o caminho até a chave, a linha da ocorrência mantida e a da descartada."""
    saida: list[dict] = []

    def linha_de(i: int) -> int:
        return texto.count("\n", 0, i) + 1

    def andar(i: int, caminho: list) -> int:
        i = _pular_branco(texto, i)
        if i < len(texto) and texto[i] == "{":
            i = _pular_branco(texto, i + 1)
            vistos: dict = {}
            while i < len(texto) and texto[i] != "}":
                inicio_chave = i
                chave, i = _DEC.raw_decode(texto, i)
                i = _pular_branco(texto, i)
                if i >= len(texto) or texto[i] != ":":
                    break
                i = _pular_branco(texto, i + 1)
                if chave in vistos:
                    saida.append({
                        "caminho": [*caminho, chave], "chave": chave,
                        "linha": linha_de(inicio_chave), "linha_anterior": linha_de(vistos[chave]),
                    })
                else:
                    vistos[chave] = inicio_chave
                i = andar(i, [*caminho, chave])
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
            return i + 1 if i < len(texto) and texto[i] == "}" else i
        if i < len(texto) and texto[i] == "[":
            i = _pular_branco(texto, i + 1)
            idx = 0
            while i < len(texto) and texto[i] != "]":
                i = andar(i, [*caminho, idx])
                i = _pular_branco(texto, i)
                if i < len(texto) and texto[i] == ",":
                    i = _pular_branco(texto, i + 1)
                idx += 1
            return i + 1 if i < len(texto) and texto[i] == "]" else i
        _, i = _DEC.raw_decode(texto, i)
        return i

    try:
        andar(0, [])
    except (ValueError, IndexError):
        return []
    return saida


def texto_do_caminho(caminho: list) -> str:
    """`['tipos', 3, 'grupo']` -> `tipos[3].grupo` (o que aparece na mensagem de erro)."""
    saida = ""
    for passo in caminho:
        saida += f"[{passo}]" if isinstance(passo, int) else (f".{passo}" if saida else str(passo))
    return saida or "(raiz)"
