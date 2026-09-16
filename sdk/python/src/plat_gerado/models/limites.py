from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Limites")


@_attrs_define
class Limites:
    """
    Attributes:
        janela_dias (int):
        linhas_max (int):
        por_tipo_por_hora (int):
    """

    janela_dias: int
    linhas_max: int
    por_tipo_por_hora: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        janela_dias = self.janela_dias

        linhas_max = self.linhas_max

        por_tipo_por_hora = self.por_tipo_por_hora

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "janela_dias": janela_dias,
                "linhas_max": linhas_max,
                "por_tipo_por_hora": por_tipo_por_hora,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        janela_dias = d.pop("janela_dias")

        linhas_max = d.pop("linhas_max")

        por_tipo_por_hora = d.pop("por_tipo_por_hora")

        limites = cls(
            janela_dias=janela_dias,
            linhas_max=linhas_max,
            por_tipo_por_hora=por_tipo_por_hora,
        )

        limites.additional_properties = d
        return limites

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
