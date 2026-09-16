from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="CsvEntrada")


@_attrs_define
class CsvEntrada:
    """O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só aceita application/json.

    Attributes:
        csv (str):
    """

    csv: str

    def to_dict(self) -> dict[str, Any]:
        csv = self.csv

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "csv": csv,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        csv = d.pop("csv")

        csv_entrada = cls(
            csv=csv,
        )

        return csv_entrada
