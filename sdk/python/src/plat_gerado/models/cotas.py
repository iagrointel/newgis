from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Cotas")


@_attrs_define
class Cotas:
    """
    Attributes:
        cota_bytes (int | None):
        cota_usuarios (int | None):
        cota_itens (int | None):
        cota_jobs_dia (int | None):
    """

    cota_bytes: int | None
    cota_usuarios: int | None
    cota_itens: int | None
    cota_jobs_dia: int | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cota_bytes: int | None
        cota_bytes = self.cota_bytes

        cota_usuarios: int | None
        cota_usuarios = self.cota_usuarios

        cota_itens: int | None
        cota_itens = self.cota_itens

        cota_jobs_dia: int | None
        cota_jobs_dia = self.cota_jobs_dia

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cota_bytes": cota_bytes,
                "cota_usuarios": cota_usuarios,
                "cota_itens": cota_itens,
                "cota_jobs_dia": cota_jobs_dia,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_cota_bytes(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cota_bytes = _parse_cota_bytes(d.pop("cota_bytes"))

        def _parse_cota_usuarios(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cota_usuarios = _parse_cota_usuarios(d.pop("cota_usuarios"))

        def _parse_cota_itens(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cota_itens = _parse_cota_itens(d.pop("cota_itens"))

        def _parse_cota_jobs_dia(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cota_jobs_dia = _parse_cota_jobs_dia(d.pop("cota_jobs_dia"))

        cotas = cls(
            cota_bytes=cota_bytes,
            cota_usuarios=cota_usuarios,
            cota_itens=cota_itens,
            cota_jobs_dia=cota_jobs_dia,
        )

        cotas.additional_properties = d
        return cotas

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
