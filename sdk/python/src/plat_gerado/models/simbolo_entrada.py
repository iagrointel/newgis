from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SimboloEntrada")


@_attrs_define
class SimboloEntrada:
    """
    Attributes:
        nome (str):
        conteudo_svg (str):
        categoria (str | Unset):  Default: 'personalizado'.
    """

    nome: str
    conteudo_svg: str
    categoria: str | Unset = "personalizado"

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        conteudo_svg = self.conteudo_svg

        categoria = self.categoria

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "conteudo_svg": conteudo_svg,
            }
        )
        if categoria is not UNSET:
            field_dict["categoria"] = categoria

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        conteudo_svg = d.pop("conteudo_svg")

        categoria = d.pop("categoria", UNSET)

        simbolo_entrada = cls(
            nome=nome,
            conteudo_svg=conteudo_svg,
            categoria=categoria,
        )

        return simbolo_entrada
