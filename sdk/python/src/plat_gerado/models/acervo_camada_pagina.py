from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.acervo_camada_publicada import AcervoCamadaPublicada


T = TypeVar("T", bound="AcervoCamadaPagina")


@_attrs_define
class AcervoCamadaPagina:
    """
    Attributes:
        total (int):
        camadas (list[AcervoCamadaPublicada]):
    """

    total: int
    camadas: list[AcervoCamadaPublicada]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        camadas = []
        for camadas_item_data in self.camadas:
            camadas_item = camadas_item_data.to_dict()
            camadas.append(camadas_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "camadas": camadas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acervo_camada_publicada import AcervoCamadaPublicada  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        camadas = []
        _camadas = d.pop("camadas")
        for camadas_item_data in _camadas:
            camadas_item = AcervoCamadaPublicada.from_dict(camadas_item_data)

            camadas.append(camadas_item)

        acervo_camada_pagina = cls(
            total=total,
            camadas=camadas,
        )

        acervo_camada_pagina.additional_properties = d
        return acervo_camada_pagina

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
