from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.merge_entrada_target_parcel_type_type_0 import MergeEntradaTargetParcelTypeType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.merge_entrada_parent_parcels_item import MergeEntradaParentParcelsItem


T = TypeVar("T", bound="MergeEntrada")


@_attrs_define
class MergeEntrada:
    """
    Attributes:
        parent_parcels (list[MergeEntradaParentParcelsItem]):
        record (str):
        gdb_version (None | str | Unset):
        session_id (None | str | Unset):
        target_parcel_type (MergeEntradaTargetParcelTypeType0 | None | Unset):
        codigo (None | str | Unset):
        default_area_unit (int | None | Unset):
        merge_into (None | str | Unset):
    """

    parent_parcels: list[MergeEntradaParentParcelsItem]
    record: str
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    target_parcel_type: MergeEntradaTargetParcelTypeType0 | None | Unset = UNSET
    codigo: None | str | Unset = UNSET
    default_area_unit: int | None | Unset = UNSET
    merge_into: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parent_parcels = []
        for parent_parcels_item_data in self.parent_parcels:
            parent_parcels_item = parent_parcels_item_data.to_dict()
            parent_parcels.append(parent_parcels_item)

        record = self.record

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

        target_parcel_type: None | str | Unset
        if isinstance(self.target_parcel_type, Unset):
            target_parcel_type = UNSET
        elif isinstance(self.target_parcel_type, MergeEntradaTargetParcelTypeType0):
            target_parcel_type = self.target_parcel_type.value
        else:
            target_parcel_type = self.target_parcel_type

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

        merge_into: None | str | Unset
        if isinstance(self.merge_into, Unset):
            merge_into = UNSET
        else:
            merge_into = self.merge_into

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parentParcels": parent_parcels,
                "record": record,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if target_parcel_type is not UNSET:
            field_dict["targetParcelType"] = target_parcel_type
        if codigo is not UNSET:
            field_dict["codigo"] = codigo
        if default_area_unit is not UNSET:
            field_dict["defaultAreaUnit"] = default_area_unit
        if merge_into is not UNSET:
            field_dict["mergeInto"] = merge_into

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.merge_entrada_parent_parcels_item import MergeEntradaParentParcelsItem  # noqa: PLC0415

        d = dict(src_dict)
        parent_parcels = []
        _parent_parcels = d.pop("parentParcels")
        for parent_parcels_item_data in _parent_parcels:
            parent_parcels_item = MergeEntradaParentParcelsItem.from_dict(parent_parcels_item_data)

            parent_parcels.append(parent_parcels_item)

        record = d.pop("record")

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

        def _parse_target_parcel_type(data: object) -> MergeEntradaTargetParcelTypeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                target_parcel_type_type_0 = MergeEntradaTargetParcelTypeType0(data)

                return target_parcel_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MergeEntradaTargetParcelTypeType0 | None | Unset, data)

        target_parcel_type = _parse_target_parcel_type(d.pop("targetParcelType", UNSET))

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

        def _parse_merge_into(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        merge_into = _parse_merge_into(d.pop("mergeInto", UNSET))

        merge_entrada = cls(
            parent_parcels=parent_parcels,
            record=record,
            gdb_version=gdb_version,
            session_id=session_id,
            target_parcel_type=target_parcel_type,
            codigo=codigo,
            default_area_unit=default_area_unit,
            merge_into=merge_into,
        )

        merge_entrada.additional_properties = d
        return merge_entrada

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
