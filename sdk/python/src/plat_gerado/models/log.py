from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.linha_log import LinhaLog


T = TypeVar("T", bound="Log")


@_attrs_define
class Log:
    """
    Attributes:
        linhas (list[LinhaLog]):
        total (int):
    """

    linhas: list[LinhaLog]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        linhas = []
        for linhas_item_data in self.linhas:
            linhas_item = linhas_item_data.to_dict()
            linhas.append(linhas_item)

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "linhas": linhas,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.linha_log import LinhaLog  # noqa: PLC0415

        d = dict(src_dict)
        linhas = []
        _linhas = d.pop("linhas")
        for linhas_item_data in _linhas:
            linhas_item = LinhaLog.from_dict(linhas_item_data)

            linhas.append(linhas_item)

        total = d.pop("total")

        log = cls(
            linhas=linhas,
            total=total,
        )

        log.additional_properties = d
        return log

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
