from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="RedefinicaoAplicarEntrada")


@_attrs_define
class RedefinicaoAplicarEntrada:
    """
    Attributes:
        token (str):
        senha (str):
    """

    token: str
    senha: str

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        senha = self.senha

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "token": token,
                "senha": senha,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        senha = d.pop("senha")

        redefinicao_aplicar_entrada = cls(
            token=token,
            senha=senha,
        )

        return redefinicao_aplicar_entrada
