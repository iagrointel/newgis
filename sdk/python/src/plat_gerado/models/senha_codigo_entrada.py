from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SenhaCodigoEntrada")


@_attrs_define
class SenhaCodigoEntrada:
    """
    Attributes:
        senha (str):
        codigo (str):
    """

    senha: str
    codigo: str

    def to_dict(self) -> dict[str, Any]:
        senha = self.senha

        codigo = self.codigo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "senha": senha,
                "codigo": codigo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        senha = d.pop("senha")

        codigo = d.pop("codigo")

        senha_codigo_entrada = cls(
            senha=senha,
            codigo=codigo,
        )

        return senha_codigo_entrada
