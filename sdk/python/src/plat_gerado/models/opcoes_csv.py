from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="OpcoesCsv")


@_attrs_define
class OpcoesCsv:
    """
    Attributes:
        separador (str | Unset):  Default: ','.
        decimal (str | Unset):  Default: '.'.
        coluna_x (None | str | Unset):
        coluna_y (None | str | Unset):
    """

    separador: str | Unset = ","
    decimal: str | Unset = "."
    coluna_x: None | str | Unset = UNSET
    coluna_y: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        separador = self.separador

        decimal = self.decimal

        coluna_x: None | str | Unset
        if isinstance(self.coluna_x, Unset):
            coluna_x = UNSET
        else:
            coluna_x = self.coluna_x

        coluna_y: None | str | Unset
        if isinstance(self.coluna_y, Unset):
            coluna_y = UNSET
        else:
            coluna_y = self.coluna_y

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if separador is not UNSET:
            field_dict["separador"] = separador
        if decimal is not UNSET:
            field_dict["decimal"] = decimal
        if coluna_x is not UNSET:
            field_dict["coluna_x"] = coluna_x
        if coluna_y is not UNSET:
            field_dict["coluna_y"] = coluna_y

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        separador = d.pop("separador", UNSET)

        decimal = d.pop("decimal", UNSET)

        def _parse_coluna_x(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        coluna_x = _parse_coluna_x(d.pop("coluna_x", UNSET))

        def _parse_coluna_y(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        coluna_y = _parse_coluna_y(d.pop("coluna_y", UNSET))

        opcoes_csv = cls(
            separador=separador,
            decimal=decimal,
            coluna_x=coluna_x,
            coluna_y=coluna_y,
        )

        return opcoes_csv
