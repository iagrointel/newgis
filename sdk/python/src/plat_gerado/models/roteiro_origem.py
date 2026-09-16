from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RoteiroOrigem")


@_attrs_define
class RoteiroOrigem:
    """
    Attributes:
        lon (float):
        lat (float):
        rotulo (None | str | Unset):
    """

    lon: float
    lat: float
    rotulo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        lon = self.lon

        lat = self.lat

        rotulo: None | str | Unset
        if isinstance(self.rotulo, Unset):
            rotulo = UNSET
        else:
            rotulo = self.rotulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "lon": lon,
                "lat": lat,
            }
        )
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        lon = d.pop("lon")

        lat = d.pop("lat")

        def _parse_rotulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rotulo = _parse_rotulo(d.pop("rotulo", UNSET))

        roteiro_origem = cls(
            lon=lon,
            lat=lat,
            rotulo=rotulo,
        )

        return roteiro_origem
