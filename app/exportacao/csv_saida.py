"""Reescrita do CSV que o ogr2ogr acabou de gravar (item L0-04-h-exportar): separador, vírgula decimal, nome
das colunas de coordenada e codificação de saída.

Por que reescrever em vez de pedir ao GDAL: o driver CSV do GDAL escreve sempre ponto decimal e nomeia as
colunas de coordenada como `X`/`Y` (opção de criação `GEOMETRY=AS_XY`); não há opção de vírgula decimal nem de
nome de coluna. O usuário brasileiro que abre o arquivo no Excel em português precisa de `;` e `,` — sem isso
toda coordenada vira texto ou é lida com a casa decimal errada.

Regra de ouro deste módulo: **uma linha por vez**. O arquivo exportado pode ter centenas de MB (uma camada de
5 milhões de feições); nada aqui lê o arquivo inteiro, nem constrói a lista de linhas. Entra `csv.reader` sobre
um arquivo aberto, sai `csv.writer` sobre outro, e no fim o novo substitui o velho (`os.replace`, atômico no
mesmo sistema de arquivos).

Só um campo que casa `NUMERO` inteiro tem o ponto trocado por vírgula: um texto com ponto (nome, data
`2026-09-06`, `1.2.3`) nunca é tocado — o casamento exige a string INTEIRA ser um número com casa decimal.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

NUMERO = re.compile(r"^-?\d+\.\d+$")
CSV_LIMITE_CAMPO = 4 * 1024 * 1024  # um campo de CSV acima de 4 MiB é dado corrompido, não dado


def reescrever(
    caminho: Path,
    *,
    separador: str = ",",
    decimal: str = ".",
    coluna_x: str | None = None,
    coluna_y: str | None = None,
    codificacao: str = "UTF-8",
) -> dict:
    """Reescreve `caminho` no lugar. Devolve `{linhas, trocas_decimais, colunas}` (contagem, para o relatório).

    `coluna_x`/`coluna_y` renomeiam APENAS o cabeçalho e apenas as colunas que o driver chamou de `X`/`Y`.
    """
    if separador == "," and decimal == "." and not coluna_x and not coluna_y and codificacao.upper() == "UTF-8":
        return {"linhas": None, "trocas_decimais": 0, "colunas": None, "reescrito": False}

    limite_antigo = csv.field_size_limit(CSV_LIMITE_CAMPO)
    destino = caminho.with_suffix(caminho.suffix + ".novo")
    linhas = trocas = 0
    colunas: list[str] = []
    try:
        with (
            caminho.open("r", encoding="utf-8", newline="") as entrada,
            destino.open("w", encoding=codificacao, newline="", errors="replace") as saida,
        ):
            leitor = csv.reader(entrada)
            escritor = csv.writer(saida, delimiter=separador, lineterminator="\r\n")
            for i, linha in enumerate(leitor):
                if i == 0:
                    linha = [
                        (coluna_x if (coluna_x and c == "X") else coluna_y if (coluna_y and c == "Y") else c)
                        for c in linha
                    ]
                    colunas = list(linha)
                elif decimal != ".":
                    nova = []
                    for c in linha:
                        if NUMERO.match(c):
                            nova.append(c.replace(".", decimal))
                            trocas += 1
                        else:
                            nova.append(c)
                    linha = nova
                escritor.writerow(linha)
                linhas += 1
    finally:
        csv.field_size_limit(limite_antigo)
    os.replace(destino, caminho)
    return {"linhas": max(linhas - 1, 0), "trocas_decimais": trocas, "colunas": colunas, "reescrito": True}
