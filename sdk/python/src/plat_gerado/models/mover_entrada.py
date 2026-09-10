from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MoverEntrada")


@_attrs_define
class MoverEntrada:
    """
    Attributes:
        pasta_id (None | str | Unset):
    """

    pasta_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        pasta_id: None | str | Unset
        if isinstance(self.pasta_id, Unset):
            pasta_id = UNSET
        else:
            pasta_id = self.pasta_id

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if pasta_id is not UNSET:
            field_dict["pasta_id"] = pasta_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_pasta_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pasta_id = _parse_pasta_id(d.pop("pasta_id", UNSET))

        mover_entrada = cls(
            pasta_id=pasta_id,
        )

        return mover_entrada
