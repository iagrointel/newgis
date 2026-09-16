from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previa_corpo_layout_type_0 import PreviaCorpoLayoutType0
    from ..models.previa_corpo_mapa_type_0 import PreviaCorpoMapaType0


T = TypeVar("T", bound="PreviaCorpo")


@_attrs_define
class PreviaCorpo:
    """
    Attributes:
        layout (None | PreviaCorpoLayoutType0 | Unset):
        layout_id (None | str | Unset):
        mapa (None | PreviaCorpoMapaType0 | Unset):
        mapa_id (None | str | Unset):
        dpi (int | Unset):  Default: 48.
        quadros (bool | Unset): desenhar os quadros pelo motor de render (mais lento) ou como área cinza Default: False.
    """

    layout: None | PreviaCorpoLayoutType0 | Unset = UNSET
    layout_id: None | str | Unset = UNSET
    mapa: None | PreviaCorpoMapaType0 | Unset = UNSET
    mapa_id: None | str | Unset = UNSET
    dpi: int | Unset = 48
    quadros: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.previa_corpo_layout_type_0 import PreviaCorpoLayoutType0  # noqa: PLC0415
        from ..models.previa_corpo_mapa_type_0 import PreviaCorpoMapaType0  # noqa: PLC0415

        layout: dict[str, Any] | None | Unset
        if isinstance(self.layout, Unset):
            layout = UNSET
        elif isinstance(self.layout, PreviaCorpoLayoutType0):
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
        elif isinstance(self.mapa, PreviaCorpoMapaType0):
            mapa = self.mapa.to_dict()
        else:
            mapa = self.mapa

        mapa_id: None | str | Unset
        if isinstance(self.mapa_id, Unset):
            mapa_id = UNSET
        else:
            mapa_id = self.mapa_id

        dpi = self.dpi

        quadros = self.quadros

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
        if dpi is not UNSET:
            field_dict["dpi"] = dpi
        if quadros is not UNSET:
            field_dict["quadros"] = quadros

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previa_corpo_layout_type_0 import PreviaCorpoLayoutType0  # noqa: PLC0415
        from ..models.previa_corpo_mapa_type_0 import PreviaCorpoMapaType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_layout(data: object) -> None | PreviaCorpoLayoutType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                layout_type_0 = PreviaCorpoLayoutType0.from_dict(data)

                return layout_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviaCorpoLayoutType0 | Unset, data)

        layout = _parse_layout(d.pop("layout", UNSET))

        def _parse_layout_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        layout_id = _parse_layout_id(d.pop("layout_id", UNSET))

        def _parse_mapa(data: object) -> None | PreviaCorpoMapaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                mapa_type_0 = PreviaCorpoMapaType0.from_dict(data)

                return mapa_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviaCorpoMapaType0 | Unset, data)

        mapa = _parse_mapa(d.pop("mapa", UNSET))

        def _parse_mapa_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mapa_id = _parse_mapa_id(d.pop("mapa_id", UNSET))

        dpi = d.pop("dpi", UNSET)

        quadros = d.pop("quadros", UNSET)

        previa_corpo = cls(
            layout=layout,
            layout_id=layout_id,
            mapa=mapa,
            mapa_id=mapa_id,
            dpi=dpi,
            quadros=quadros,
        )

        previa_corpo.additional_properties = d
        return previa_corpo

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
