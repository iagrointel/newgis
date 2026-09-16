from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.divide_entrada_divide_option_type_0 import DivideEntradaDivideOptionType0
from ..models.divide_entrada_divide_parcel_type_type_0 import DivideEntradaDivideParcelTypeType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="DivideEntrada")


@_attrs_define
class DivideEntrada:
    """Divide na forma da doc (divideOption + bearing) OU com linha de corte direta (campo
    `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11).

        Attributes:
            record (str):
            gdb_version (None | str | Unset):
            session_id (None | str | Unset):
            divide_parcel_guid (None | str | Unset):
            divide_parcel_type (DivideEntradaDivideParcelTypeType0 | None | Unset):
            divide_option (DivideEntradaDivideOptionType0 | None | Unset):
            divide_number_of_parts (int | Unset):  Default: 2.
            divide_part_area_or_width (float | Unset):  Default: 0.0.
            divide_line_bearing (float | None | Unset):
            divide_left_side (bool | Unset):  Default: True.
            divide_distribute_remainder (bool | Unset):  Default: False.
            linha (list[list[float]] | None | Unset):
    """

    record: str
    gdb_version: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    divide_parcel_guid: None | str | Unset = UNSET
    divide_parcel_type: DivideEntradaDivideParcelTypeType0 | None | Unset = UNSET
    divide_option: DivideEntradaDivideOptionType0 | None | Unset = UNSET
    divide_number_of_parts: int | Unset = 2
    divide_part_area_or_width: float | Unset = 0.0
    divide_line_bearing: float | None | Unset = UNSET
    divide_left_side: bool | Unset = True
    divide_distribute_remainder: bool | Unset = False
    linha: list[list[float]] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

        divide_parcel_guid: None | str | Unset
        if isinstance(self.divide_parcel_guid, Unset):
            divide_parcel_guid = UNSET
        else:
            divide_parcel_guid = self.divide_parcel_guid

        divide_parcel_type: None | str | Unset
        if isinstance(self.divide_parcel_type, Unset):
            divide_parcel_type = UNSET
        elif isinstance(self.divide_parcel_type, DivideEntradaDivideParcelTypeType0):
            divide_parcel_type = self.divide_parcel_type.value
        else:
            divide_parcel_type = self.divide_parcel_type

        divide_option: None | str | Unset
        if isinstance(self.divide_option, Unset):
            divide_option = UNSET
        elif isinstance(self.divide_option, DivideEntradaDivideOptionType0):
            divide_option = self.divide_option.value
        else:
            divide_option = self.divide_option

        divide_number_of_parts = self.divide_number_of_parts

        divide_part_area_or_width = self.divide_part_area_or_width

        divide_line_bearing: float | None | Unset
        if isinstance(self.divide_line_bearing, Unset):
            divide_line_bearing = UNSET
        else:
            divide_line_bearing = self.divide_line_bearing

        divide_left_side = self.divide_left_side

        divide_distribute_remainder = self.divide_distribute_remainder

        linha: list[list[float]] | None | Unset
        if isinstance(self.linha, Unset):
            linha = UNSET
        elif isinstance(self.linha, list):
            linha = []
            for linha_type_0_item_data in self.linha:
                linha_type_0_item = linha_type_0_item_data

                linha.append(linha_type_0_item)

        else:
            linha = self.linha

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
        if divide_parcel_guid is not UNSET:
            field_dict["divideParcelGuid"] = divide_parcel_guid
        if divide_parcel_type is not UNSET:
            field_dict["divideParcelType"] = divide_parcel_type
        if divide_option is not UNSET:
            field_dict["divideOption"] = divide_option
        if divide_number_of_parts is not UNSET:
            field_dict["divideNumberOfParts"] = divide_number_of_parts
        if divide_part_area_or_width is not UNSET:
            field_dict["dividePartAreaOrWidth"] = divide_part_area_or_width
        if divide_line_bearing is not UNSET:
            field_dict["divideLineBearing"] = divide_line_bearing
        if divide_left_side is not UNSET:
            field_dict["divideLeftSide"] = divide_left_side
        if divide_distribute_remainder is not UNSET:
            field_dict["divideDistributeRemainder"] = divide_distribute_remainder
        if linha is not UNSET:
            field_dict["linha"] = linha

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
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

        def _parse_divide_parcel_guid(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        divide_parcel_guid = _parse_divide_parcel_guid(d.pop("divideParcelGuid", UNSET))

        def _parse_divide_parcel_type(data: object) -> DivideEntradaDivideParcelTypeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                divide_parcel_type_type_0 = DivideEntradaDivideParcelTypeType0(data)

                return divide_parcel_type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DivideEntradaDivideParcelTypeType0 | None | Unset, data)

        divide_parcel_type = _parse_divide_parcel_type(d.pop("divideParcelType", UNSET))

        def _parse_divide_option(data: object) -> DivideEntradaDivideOptionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                divide_option_type_0 = DivideEntradaDivideOptionType0(data)

                return divide_option_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DivideEntradaDivideOptionType0 | None | Unset, data)

        divide_option = _parse_divide_option(d.pop("divideOption", UNSET))

        divide_number_of_parts = d.pop("divideNumberOfParts", UNSET)

        divide_part_area_or_width = d.pop("dividePartAreaOrWidth", UNSET)

        def _parse_divide_line_bearing(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        divide_line_bearing = _parse_divide_line_bearing(d.pop("divideLineBearing", UNSET))

        divide_left_side = d.pop("divideLeftSide", UNSET)

        divide_distribute_remainder = d.pop("divideDistributeRemainder", UNSET)

        def _parse_linha(data: object) -> list[list[float]] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                linha_type_0 = []
                _linha_type_0 = data
                for linha_type_0_item_data in _linha_type_0:
                    linha_type_0_item = cast(list[float], linha_type_0_item_data)

                    linha_type_0.append(linha_type_0_item)

                return linha_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[list[float]] | None | Unset, data)

        linha = _parse_linha(d.pop("linha", UNSET))

        divide_entrada = cls(
            record=record,
            gdb_version=gdb_version,
            session_id=session_id,
            divide_parcel_guid=divide_parcel_guid,
            divide_parcel_type=divide_parcel_type,
            divide_option=divide_option,
            divide_number_of_parts=divide_number_of_parts,
            divide_part_area_or_width=divide_part_area_or_width,
            divide_line_bearing=divide_line_bearing,
            divide_left_side=divide_left_side,
            divide_distribute_remainder=divide_distribute_remainder,
            linha=linha,
        )

        divide_entrada.additional_properties = d
        return divide_entrada

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
