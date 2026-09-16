from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.extent import Extent


T = TypeVar("T", bound="ReconstructEntrada")


@_attrs_define
class ReconstructEntrada:
    """
    Attributes:
        extent (Extent): Envelope da doc (buildExtent/extent). spatialReference é aceito e ignorado (SRID fixo).
        record (str):
        gdb_version (None | str | Unset):
        session_id (None | str | Unset):
    """

    extent: Extent
    record: str
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        extent = self.extent.to_dict()

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "extent": extent,
                "record": record,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.extent import Extent  # noqa: PLC0415

        d = dict(src_dict)
        extent = Extent.from_dict(d.pop("extent"))

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

        reconstruct_entrada = cls(
            extent=extent,
            record=record,
            gdb_version=gdb_version,
            session_id=session_id,
        )

        reconstruct_entrada.additional_properties = d
        return reconstruct_entrada

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
