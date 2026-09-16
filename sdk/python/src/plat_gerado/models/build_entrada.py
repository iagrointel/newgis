from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.build_entrada_tipo_type_0 import BuildEntradaTipoType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.extent import Extent


T = TypeVar("T", bound="BuildEntrada")


@_attrs_define
class BuildEntrada:
    """
    Attributes:
        record (str):
        gdb_version (None | str | Unset):
        session_id (None | str | Unset):
        tipo (BuildEntradaTipoType0 | None | Unset):
        build_extent (Extent | None | Unset):
    """

    record: str
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    tipo: BuildEntradaTipoType0 | None | Unset = UNSET
    build_extent: Extent | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.extent import Extent  # noqa: PLC0415

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

        tipo: None | str | Unset
        if isinstance(self.tipo, Unset):
            tipo = UNSET
        elif isinstance(self.tipo, BuildEntradaTipoType0):
            tipo = self.tipo.value
        else:
            tipo = self.tipo

        build_extent: dict[str, Any] | None | Unset
        if isinstance(self.build_extent, Unset):
            build_extent = UNSET
        elif isinstance(self.build_extent, Extent):
            build_extent = self.build_extent.to_dict()
        else:
            build_extent = self.build_extent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "record": record,
            }
        )
        if gdb_version is not UNSET:
            field_dict["gdbVersion"] = gdb_version
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if build_extent is not UNSET:
            field_dict["buildExtent"] = build_extent

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.extent import Extent  # noqa: PLC0415

        d = dict(src_dict)
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

        def _parse_tipo(data: object) -> BuildEntradaTipoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tipo_type_0 = BuildEntradaTipoType0(data)

                return tipo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BuildEntradaTipoType0 | None | Unset, data)

        tipo = _parse_tipo(d.pop("tipo", UNSET))

        def _parse_build_extent(data: object) -> Extent | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                build_extent_type_0 = Extent.from_dict(data)

                return build_extent_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Extent | None | Unset, data)

        build_extent = _parse_build_extent(d.pop("buildExtent", UNSET))

        build_entrada = cls(
            record=record,
            gdb_version=gdb_version,
            session_id=session_id,
            tipo=tipo,
            build_extent=build_extent,
        )

        build_entrada.additional_properties = d
        return build_entrada

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
