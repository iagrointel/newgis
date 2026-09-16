from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="PonteEntrada")


@_attrs_define
class PonteEntrada:
    """
    Attributes:
        conexao (str):
        formulario (str):
        projeto (int):
        conteudo (str):
    """

    conexao: str
    formulario: str
    projeto: int
    conteudo: str

    def to_dict(self) -> dict[str, Any]:
        conexao = self.conexao

        formulario = self.formulario

        projeto = self.projeto

        conteudo = self.conteudo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "conexao": conexao,
                "formulario": formulario,
                "projeto": projeto,
                "conteudo": conteudo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conexao = d.pop("conexao")

        formulario = d.pop("formulario")

        projeto = d.pop("projeto")

        conteudo = d.pop("conteudo")

        ponte_entrada = cls(
            conexao=conexao,
            formulario=formulario,
            projeto=projeto,
            conteudo=conteudo,
        )

        return ponte_entrada
