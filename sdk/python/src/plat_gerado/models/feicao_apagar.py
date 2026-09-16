from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FeicaoApagar")


@_attrs_define
class FeicaoApagar:
    """
    Attributes:
        id (str):
        versao (int | None | Unset):
    """

    id: str
    versao: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
            }
        )
        if versao is not UNSET:
            field_dict["versao"] = versao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        feicao_apagar = cls(
            id=id,
            versao=versao,
        )

        return feicao_apagar
