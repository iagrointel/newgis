from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="VersionarEntrada")


@_attrs_define
class VersionarEntrada:
    """
    Attributes:
        ramos_max (int | None | Unset):
    """

    ramos_max: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        ramos_max: int | None | Unset
        if isinstance(self.ramos_max, Unset):
            ramos_max = UNSET
        else:
            ramos_max = self.ramos_max

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if ramos_max is not UNSET:
            field_dict["ramos_max"] = ramos_max

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_ramos_max(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ramos_max = _parse_ramos_max(d.pop("ramos_max", UNSET))

        versionar_entrada = cls(
            ramos_max=ramos_max,
        )

        return versionar_entrada
