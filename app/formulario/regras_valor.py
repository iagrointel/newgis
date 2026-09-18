"""Uma regra só, usada pelos DOIS caminhos de escrita que o item L5-03-form-builder promete cobrir
(`app/edicao/servico.py::validar_atributos`, edição web, e `app/formulario/motor.py::validar_dados_livre`,
PWA de campo): o que conta como "campo obrigatório não preenchido".

Antes, os dois lugares testavam `nome not in limpos or limpos[nome] is None` — e uma string vazia (`""`),
que é o que um formulário de navegador manda quando o usuário não digita nada num campo de texto, passava
pelos dois. O adversário do T9 mostrou isso nos dois caminhos com a mesma submissão.

Vazio aqui é: chave ausente, `None`, string só de espaço em branco, e lista/dicionário sem nenhum item
(campo de múltipla escolha ou anexo sem nada escolhido). `0`, `0.0` e `False` NÃO são vazios — são valores
preenchidos e continuam passando."""

from __future__ import annotations

from typing import Any

AUSENTE = object()


def valor_vazio(valor: Any) -> bool:
    if valor is AUSENTE or valor is None:
        return True
    if isinstance(valor, str):
        return valor.strip() == ""
    if isinstance(valor, (list, tuple, set, dict)):
        return len(valor) == 0
    return False


def campo_nao_preenchido(valores: dict, nome: str) -> bool:
    """`True` quando o campo obrigatório `nome` não foi preenchido em `valores`."""
    return valor_vazio(valores.get(nome, AUSENTE))


__all__ = ["AUSENTE", "valor_vazio", "campo_nao_preenchido"]
