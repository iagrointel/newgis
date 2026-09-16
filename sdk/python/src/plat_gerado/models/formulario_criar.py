from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FormularioCriar")


@_attrs_define
class FormularioCriar:
    """
    Attributes:
        nome (str | Unset):  Default: 'Formulário'.
    """

    nome: str | Unset = "Formulário"

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome", UNSET)

        formulario_criar = cls(
            nome=nome,
        )

        return formulario_criar
