from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PastaEntrada")


@_attrs_define
class PastaEntrada:
    """
    Attributes:
        nome (str):
        pai_id (None | str | Unset):
    """

    nome: str
    pai_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        pai_id: None | str | Unset
        if isinstance(self.pai_id, Unset):
            pai_id = UNSET
        else:
            pai_id = self.pai_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
            }
        )
        if pai_id is not UNSET:
            field_dict["pai_id"] = pai_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        def _parse_pai_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pai_id = _parse_pai_id(d.pop("pai_id", UNSET))

        pasta_entrada = cls(
            nome=nome,
            pai_id=pai_id,
        )

        return pasta_entrada
