from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.limites import Limites
    from ..models.tipo_relatorio import TipoRelatorio


T = TypeVar("T", bound="TiposRelatorio")


@_attrs_define
class TiposRelatorio:
    """
    Attributes:
        tipos (list[TipoRelatorio]):
        limites (Limites):
    """

    tipos: list[TipoRelatorio]
    limites: Limites
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipos = []
        for tipos_item_data in self.tipos:
            tipos_item = tipos_item_data.to_dict()
            tipos.append(tipos_item)

        limites = self.limites.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipos": tipos,
                "limites": limites,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.limites import Limites  # noqa: PLC0415
        from ..models.tipo_relatorio import TipoRelatorio  # noqa: PLC0415

        d = dict(src_dict)
        tipos = []
        _tipos = d.pop("tipos")
        for tipos_item_data in _tipos:
            tipos_item = TipoRelatorio.from_dict(tipos_item_data)

            tipos.append(tipos_item)

        limites = Limites.from_dict(d.pop("limites"))

        tipos_relatorio = cls(
            tipos=tipos,
            limites=limites,
        )

        tipos_relatorio.additional_properties = d
        return tipos_relatorio

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
