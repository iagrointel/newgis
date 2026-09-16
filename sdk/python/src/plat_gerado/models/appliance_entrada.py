from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ApplianceEntrada")


@_attrs_define
class ApplianceEntrada:
    """
    Attributes:
        chave (str):
        nome (str):
    """

    chave: str
    nome: str

    def to_dict(self) -> dict[str, Any]:
        chave = self.chave

        nome = self.nome

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "chave": chave,
                "nome": nome,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        chave = d.pop("chave")

        nome = d.pop("nome")

        appliance_entrada = cls(
            chave=chave,
            nome=nome,
        )

        return appliance_entrada
