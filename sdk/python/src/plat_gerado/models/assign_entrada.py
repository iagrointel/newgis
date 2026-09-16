from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.assign_entrada_writeattribute import AssignEntradaWriteattribute
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.assign_entrada_parcel_features_item import AssignEntradaParcelFeaturesItem


T = TypeVar("T", bound="AssignEntrada")


@_attrs_define
class AssignEntrada:
    """
    Attributes:
        parcel_features (list[AssignEntradaParcelFeaturesItem]):
        record (str):
        write_attribute (AssignEntradaWriteattribute):
        gdb_version (None | str | Unset):
        session_id (None | str | Unset):
    """

    parcel_features: list[AssignEntradaParcelFeaturesItem]
    record: str
    write_attribute: AssignEntradaWriteattribute
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parcel_features = []
        for parcel_features_item_data in self.parcel_features:
            parcel_features_item = parcel_features_item_data.to_dict()
            parcel_features.append(parcel_features_item)

        record = self.record

        write_attribute = self.write_attribute.value

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parcelFeatures": parcel_features,
                "record": record,
                "writeAttribute": write_attribute,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.assign_entrada_parcel_features_item import AssignEntradaParcelFeaturesItem  # noqa: PLC0415

        d = dict(src_dict)
        parcel_features = []
        _parcel_features = d.pop("parcelFeatures")
        for parcel_features_item_data in _parcel_features:
            parcel_features_item = AssignEntradaParcelFeaturesItem.from_dict(parcel_features_item_data)

            parcel_features.append(parcel_features_item)

        record = d.pop("record")

        write_attribute = AssignEntradaWriteattribute(d.pop("writeAttribute"))

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

        assign_entrada = cls(
            parcel_features=parcel_features,
            record=record,
            write_attribute=write_attribute,
            gdb_version=gdb_version,
            session_id=session_id,
        )

        assign_entrada.additional_properties = d
        return assign_entrada

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
