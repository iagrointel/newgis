from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tracado_area_suja_resultado_area_suja_type_0 import TracadoAreaSujaResultadoAreaSujaType0


T = TypeVar("T", bound="TracadoAreaSujaResultado")


@_attrs_define
class TracadoAreaSujaResultado:
    """
    Attributes:
        rede_id (str):
        cruza_area_suja (bool):
        bloqueado (bool):
        modo (str):
        area_suja (None | TracadoAreaSujaResultadoAreaSujaType0 | Unset):
    """

    rede_id: str
    cruza_area_suja: bool
    bloqueado: bool
    modo: str
    area_suja: None | TracadoAreaSujaResultadoAreaSujaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tracado_area_suja_resultado_area_suja_type_0 import (
            TracadoAreaSujaResultadoAreaSujaType0,  # noqa: PLC0415
        )

        rede_id = self.rede_id

        cruza_area_suja = self.cruza_area_suja

        bloqueado = self.bloqueado

        modo = self.modo

        area_suja: dict[str, Any] | None | Unset
        if isinstance(self.area_suja, Unset):
            area_suja = UNSET
        elif isinstance(self.area_suja, TracadoAreaSujaResultadoAreaSujaType0):
            area_suja = self.area_suja.to_dict()
        else:
            area_suja = self.area_suja

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "cruza_area_suja": cruza_area_suja,
                "bloqueado": bloqueado,
                "modo": modo,
            }
        )
        if area_suja is not UNSET:
            field_dict["area_suja"] = area_suja

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tracado_area_suja_resultado_area_suja_type_0 import (
            TracadoAreaSujaResultadoAreaSujaType0,  # noqa: PLC0415
        )

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        cruza_area_suja = d.pop("cruza_area_suja")

        bloqueado = d.pop("bloqueado")

        modo = d.pop("modo")

        def _parse_area_suja(data: object) -> None | TracadoAreaSujaResultadoAreaSujaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                area_suja_type_0 = TracadoAreaSujaResultadoAreaSujaType0.from_dict(data)

                return area_suja_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TracadoAreaSujaResultadoAreaSujaType0 | Unset, data)

        area_suja = _parse_area_suja(d.pop("area_suja", UNSET))

        tracado_area_suja_resultado = cls(
            rede_id=rede_id,
            cruza_area_suja=cruza_area_suja,
            bloqueado=bloqueado,
            modo=modo,
            area_suja=area_suja,
        )

        tracado_area_suja_resultado.additional_properties = d
        return tracado_area_suja_resultado

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
