from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.clip_entrada_clipoption import ClipEntradaClipoption
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.clip_entrada_clipping_geometry_type_0 import ClipEntradaClippingGeometryType0
    from ..models.clip_entrada_clipping_parcels_type_0_item import ClipEntradaClippingParcelsType0Item
    from ..models.clip_entrada_parent_parcels_item import ClipEntradaParentParcelsItem


T = TypeVar("T", bound="ClipEntrada")


@_attrs_define
class ClipEntrada:
    """
    Attributes:
        parent_parcels (list[ClipEntradaParentParcelsItem]):
        record (str):
        clip_option (ClipEntradaClipoption):
        gdb_version (None | str | Unset):
        session_id (None | str | Unset):
        clipping_parcels (list[ClipEntradaClippingParcelsType0Item] | None | Unset):
        clipping_geometry (ClipEntradaClippingGeometryType0 | None | Unset):
        codigo (None | str | Unset):
        default_area_unit (int | None | Unset):
    """

    parent_parcels: list[ClipEntradaParentParcelsItem]
    record: str
    clip_option: ClipEntradaClipoption
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    clipping_parcels: list[ClipEntradaClippingParcelsType0Item] | None | Unset = UNSET
    clipping_geometry: ClipEntradaClippingGeometryType0 | None | Unset = UNSET
    codigo: None | str | Unset = UNSET
    default_area_unit: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.clip_entrada_clipping_geometry_type_0 import ClipEntradaClippingGeometryType0  # noqa: PLC0415

        parent_parcels = []
        for parent_parcels_item_data in self.parent_parcels:
            parent_parcels_item = parent_parcels_item_data.to_dict()
            parent_parcels.append(parent_parcels_item)

        record = self.record

        clip_option = self.clip_option.value

        gdb_version: None | str | Unset
        if isinstance(self.gdb_version, Unset):
            gdb_version = UNSET
        else:
            gdb_version = self.gdb_version

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        clipping_parcels: list[dict[str, Any]] | None | Unset
        if isinstance(self.clipping_parcels, Unset):
            clipping_parcels = UNSET
        elif isinstance(self.clipping_parcels, list):
            clipping_parcels = []
            for clipping_parcels_type_0_item_data in self.clipping_parcels:
                clipping_parcels_type_0_item = clipping_parcels_type_0_item_data.to_dict()
                clipping_parcels.append(clipping_parcels_type_0_item)

        else:
            clipping_parcels = self.clipping_parcels

        clipping_geometry: dict[str, Any] | None | Unset
        if isinstance(self.clipping_geometry, Unset):
            clipping_geometry = UNSET
        elif isinstance(self.clipping_geometry, ClipEntradaClippingGeometryType0):
            clipping_geometry = self.clipping_geometry.to_dict()
        else:
            clipping_geometry = self.clipping_geometry

        codigo: None | str | Unset
        if isinstance(self.codigo, Unset):
            codigo = UNSET
        else:
            codigo = self.codigo

        default_area_unit: int | None | Unset
        if isinstance(self.default_area_unit, Unset):
            default_area_unit = UNSET
        else:
            default_area_unit = self.default_area_unit

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parentParcels": parent_parcels,
                "record": record,
                "clipOption": clip_option,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if clipping_parcels is not UNSET:
            field_dict["clippingParcels"] = clipping_parcels
        if clipping_geometry is not UNSET:
            field_dict["clippingGeometry"] = clipping_geometry
        if codigo is not UNSET:
            field_dict["codigo"] = codigo
        if default_area_unit is not UNSET:
            field_dict["defaultAreaUnit"] = default_area_unit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.clip_entrada_clipping_geometry_type_0 import ClipEntradaClippingGeometryType0  # noqa: PLC0415
        from ..models.clip_entrada_clipping_parcels_type_0_item import (
            ClipEntradaClippingParcelsType0Item,  # noqa: PLC0415
        )
        from ..models.clip_entrada_parent_parcels_item import ClipEntradaParentParcelsItem  # noqa: PLC0415

        d = dict(src_dict)
        parent_parcels = []
        _parent_parcels = d.pop("parentParcels")
        for parent_parcels_item_data in _parent_parcels:
            parent_parcels_item = ClipEntradaParentParcelsItem.from_dict(parent_parcels_item_data)

            parent_parcels.append(parent_parcels_item)

        record = d.pop("record")

        clip_option = ClipEntradaClipoption(d.pop("clipOption"))

        def _parse_gdb_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gdb_version = _parse_gdb_version(d.pop("gdbVersion", UNSET))

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("sessionId", UNSET))

        def _parse_clipping_parcels(data: object) -> list[ClipEntradaClippingParcelsType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                clipping_parcels_type_0 = []
                _clipping_parcels_type_0 = data
                for clipping_parcels_type_0_item_data in _clipping_parcels_type_0:
                    clipping_parcels_type_0_item = ClipEntradaClippingParcelsType0Item.from_dict(
                        clipping_parcels_type_0_item_data
                    )

                    clipping_parcels_type_0.append(clipping_parcels_type_0_item)

                return clipping_parcels_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ClipEntradaClippingParcelsType0Item] | None | Unset, data)

        clipping_parcels = _parse_clipping_parcels(d.pop("clippingParcels", UNSET))

        def _parse_clipping_geometry(data: object) -> ClipEntradaClippingGeometryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                clipping_geometry_type_0 = ClipEntradaClippingGeometryType0.from_dict(data)

                return clipping_geometry_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClipEntradaClippingGeometryType0 | None | Unset, data)

        clipping_geometry = _parse_clipping_geometry(d.pop("clippingGeometry", UNSET))

        def _parse_codigo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo = _parse_codigo(d.pop("codigo", UNSET))

        def _parse_default_area_unit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        default_area_unit = _parse_default_area_unit(d.pop("defaultAreaUnit", UNSET))

        clip_entrada = cls(
            parent_parcels=parent_parcels,
            record=record,
            clip_option=clip_option,
            gdb_version=gdb_version,
            session_id=session_id,
            clipping_parcels=clipping_parcels,
            clipping_geometry=clipping_geometry,
            codigo=codigo,
            default_area_unit=default_area_unit,
        )

        clip_entrada.additional_properties = d
        return clip_entrada

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
