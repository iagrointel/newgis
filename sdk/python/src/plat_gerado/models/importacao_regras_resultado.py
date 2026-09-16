from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ImportacaoRegrasResultado")


@_attrs_define
class ImportacaoRegrasResultado:
    """
    Attributes:
        rede_id (str):
        total (int):
        sha256 (str):
        bytes_ (int):
    """

    rede_id: str
    total: int
    sha256: str
    bytes_: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        total = self.total

        sha256 = self.sha256

        bytes_ = self.bytes_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "total": total,
                "sha256": sha256,
                "bytes": bytes_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        total = d.pop("total")

        sha256 = d.pop("sha256")

        bytes_ = d.pop("bytes")

        importacao_regras_resultado = cls(
            rede_id=rede_id,
            total=total,
            sha256=sha256,
            bytes_=bytes_,
        )

        importacao_regras_resultado.additional_properties = d
        return importacao_regras_resultado

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
