from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="Crs")


@_attrs_define
class Crs:
    """
    Attributes:
        srid (int):
    """

    srid: int

    def to_dict(self) -> dict[str, Any]:
        srid = self.srid

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "srid": srid,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        srid = d.pop("srid")

        crs = cls(
            srid=srid,
        )

        return crs
