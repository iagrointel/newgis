from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.layout_corpo_layout_type_0 import LayoutCorpoLayoutType0
    from ..models.layout_corpo_mapa_type_0 import LayoutCorpoMapaType0


T = TypeVar("T", bound="LayoutCorpo")


@_attrs_define
class LayoutCorpo:
    """
    Attributes:
        layout (LayoutCorpoLayoutType0 | None | Unset):
        layout_id (None | str | Unset):
        mapa (LayoutCorpoMapaType0 | None | Unset):
        mapa_id (None | str | Unset):
    """

    layout: LayoutCorpoLayoutType0 | None | Unset = UNSET
    layout_id: None | str | Unset = UNSET
    mapa: LayoutCorpoMapaType0 | None | Unset = UNSET
    mapa_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.layout_corpo_layout_type_0 import LayoutCorpoLayoutType0  # noqa: PLC0415
        from ..models.layout_corpo_mapa_type_0 import LayoutCorpoMapaType0  # noqa: PLC0415

        layout: dict[str, Any] | None | Unset
        if isinstance(self.layout, Unset):
            layout = UNSET
        elif isinstance(self.layout, LayoutCorpoLayoutType0):
            layout = self.layout.to_dict()
        else:
            layout = self.layout

        layout_id: None | str | Unset
        if isinstance(self.layout_id, Unset):
            layout_id = UNSET
        else:
            layout_id = self.layout_id

        mapa: dict[str, Any] | None | Unset
        if isinstance(self.mapa, Unset):
            mapa = UNSET
        elif isinstance(self.mapa, LayoutCorpoMapaType0):
            mapa = self.mapa.to_dict()
        else:
            mapa = self.mapa

        mapa_id: None | str | Unset
        if isinstance(self.mapa_id, Unset):
            mapa_id = UNSET
        else:
            mapa_id = self.mapa_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if layout is not UNSET:
            field_dict["layout"] = layout
        if layout_id is not UNSET:
            field_dict["layout_id"] = layout_id
        if mapa is not UNSET:
            field_dict["mapa"] = mapa
        if mapa_id is not UNSET:
            field_dict["mapa_id"] = mapa_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.layout_corpo_layout_type_0 import LayoutCorpoLayoutType0  # noqa: PLC0415
        from ..models.layout_corpo_mapa_type_0 import LayoutCorpoMapaType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_layout(data: object) -> LayoutCorpoLayoutType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                layout_type_0 = LayoutCorpoLayoutType0.from_dict(data)

                return layout_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LayoutCorpoLayoutType0 | None | Unset, data)

        layout = _parse_layout(d.pop("layout", UNSET))

        def _parse_layout_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        layout_id = _parse_layout_id(d.pop("layout_id", UNSET))

        def _parse_mapa(data: object) -> LayoutCorpoMapaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                mapa_type_0 = LayoutCorpoMapaType0.from_dict(data)

                return mapa_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LayoutCorpoMapaType0 | None | Unset, data)

        mapa = _parse_mapa(d.pop("mapa", UNSET))

        def _parse_mapa_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mapa_id = _parse_mapa_id(d.pop("mapa_id", UNSET))

        layout_corpo = cls(
            layout=layout,
            layout_id=layout_id,
            mapa=mapa,
            mapa_id=mapa_id,
        )

        layout_corpo.additional_properties = d
        return layout_corpo

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
