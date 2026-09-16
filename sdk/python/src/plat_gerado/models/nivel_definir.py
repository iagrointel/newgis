from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NivelDefinir")


@_attrs_define
class NivelDefinir:
    """
    Attributes:
        componente (str): nome do logger (app.consulta), prefixo de rota (rota:/api/tiles) ou * (global)
        nivel (str):
        minutos (float | None | Unset): prazo; None = até ser removido
    """

    componente: str
    nivel: str
    minutos: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        componente = self.componente

        nivel = self.nivel

        minutos: float | None | Unset
        if isinstance(self.minutos, Unset):
            minutos = UNSET
        else:
            minutos = self.minutos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "componente": componente,
                "nivel": nivel,
            }
        )
        if minutos is not UNSET:
            field_dict["minutos"] = minutos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        componente = d.pop("componente")

        nivel = d.pop("nivel")

        def _parse_minutos(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        minutos = _parse_minutos(d.pop("minutos", UNSET))

        nivel_definir = cls(
            componente=componente,
            nivel=nivel,
            minutos=minutos,
        )

        nivel_definir.additional_properties = d
        return nivel_definir

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
