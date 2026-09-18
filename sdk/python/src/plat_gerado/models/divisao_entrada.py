from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="DivisaoEntrada")


@_attrs_define
class DivisaoEntrada:
    """
    Attributes:
        id (str):
        versao (int):
        ponto (list[float]):
    """

    id: str
    versao: int
    ponto: list[float]

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        versao = self.versao

        ponto = self.ponto

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
                "versao": versao,
                "ponto": ponto,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        versao = d.pop("versao")

        ponto = cast(list[float], d.pop("ponto"))

        divisao_entrada = cls(
            id=id,
            versao=versao,
            ponto=ponto,
        )

        return divisao_entrada
