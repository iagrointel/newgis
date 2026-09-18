from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Agora")


@_attrs_define
class Agora:
    """
    Attributes:
        bytes_total (int):
        itens (int):
        itens_lixeira (int):
        usuarios_total (int):
        jobs_hoje (int):
    """

    bytes_total: int
    itens: int
    itens_lixeira: int
    usuarios_total: int
    jobs_hoje: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bytes_total = self.bytes_total

        itens = self.itens

        itens_lixeira = self.itens_lixeira

        usuarios_total = self.usuarios_total

        jobs_hoje = self.jobs_hoje

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "bytes_total": bytes_total,
                "itens": itens,
                "itens_lixeira": itens_lixeira,
                "usuarios_total": usuarios_total,
                "jobs_hoje": jobs_hoje,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        bytes_total = d.pop("bytes_total")

        itens = d.pop("itens")

        itens_lixeira = d.pop("itens_lixeira")

        usuarios_total = d.pop("usuarios_total")

        jobs_hoje = d.pop("jobs_hoje")

        agora = cls(
            bytes_total=bytes_total,
            itens=itens,
            itens_lixeira=itens_lixeira,
            usuarios_total=usuarios_total,
            jobs_hoje=jobs_hoje,
        )

        agora.additional_properties = d
        return agora

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
