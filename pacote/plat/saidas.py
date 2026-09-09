"""Saídas de ferramenta-script (item L2-16-c-script-vira-ferramenta): o contrato entre um script
executado como ferramenta e a casa. O script NÃO grava itens de catálogo por conta própria — o
token do contêiner é de leitura (L2-16-b), e a procedência (sha256 do texto executado + versão)
só pode ser afirmada por quem executou. O script declara os valores de cada saída declarada no
cabeçalho com `gravar(nome, valor)`; o job lê o arquivo no fim, recusa saída fora do declarado e
registra o item `ferramenta_resultado`.

    from plat import saidas
    saidas.gravar("buffer", colecao_de_feicoes)

O caminho do arquivo vem do ambiente (PLAT_SAIDA_DIR, posto pelo job); fora de execução de
ferramenta, gravar cria `saida.json` no diretório corrente — o script roda sempre igual nos dois
lugares.
"""

from __future__ import annotations

import json
import os

NOME_ARQUIVO = "saida.json"


def caminho() -> str:
    """Arquivo onde as saídas da execução são acumuladas (PLAT_SAIDA_DIR/saida.json)."""
    diretorio = os.environ.get("PLAT_SAIDA_DIR") or os.getcwd()
    return os.path.join(diretorio, NOME_ARQUIVO)


def gravar(nome: str, valor) -> dict:
    """Acumula uma saída declarada no cabeçalho. Chamada duas vezes com o mesmo nome SUBSTITUI
    (a última escrita é a que vale); devolve o conteúdo atual do arquivo."""
    if not nome or not all(c.isalnum() or c == "_" for c in nome) or len(nome) > 80:
        raise ValueError(f"nome de saída inválido: {nome!r} (letras, dígitos e _, até 80)")
    atual = {}
    destino = caminho()
    if os.path.exists(destino):
        try:
            with open(destino, encoding="utf-8") as arq:
                carregado = json.load(arq)
            if isinstance(carregado, dict):
                atual = carregado
        except (ValueError, OSError):
            atual = {}  # arquivo truncado por escrita interrompida: recomeça o acúmulo
    atual[nome] = valor
    com_temp = destino + ".tmp"
    with open(com_temp, "w", encoding="utf-8") as arq:
        json.dump(atual, arq, ensure_ascii=False, default=str)
    os.replace(com_temp, destino)  # atômico no mesmo sistema de arquivos
    return atual
