from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.papeis_perfis_item import PapeisPerfisItem
    from ..models.papel import Papel


T = TypeVar("T", bound="Papeis")


@_attrs_define
class Papeis:
    """
    Attributes:
        perfis (list[PapeisPerfisItem]):
        personalizados (list[Papel]):
    """

    perfis: list[PapeisPerfisItem]
    personalizados: list[Papel]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        perfis = []
        for perfis_item_data in self.perfis:
            perfis_item = perfis_item_data.to_dict()
            perfis.append(perfis_item)

        personalizados = []
        for personalizados_item_data in self.personalizados:
            personalizados_item = personalizados_item_data.to_dict()
            personalizados.append(personalizados_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "perfis": perfis,
                "personalizados": personalizados,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.papeis_perfis_item import PapeisPerfisItem  # noqa: PLC0415
        from ..models.papel import Papel  # noqa: PLC0415

        d = dict(src_dict)
        perfis = []
        _perfis = d.pop("perfis")
        for perfis_item_data in _perfis:
            perfis_item = PapeisPerfisItem.from_dict(perfis_item_data)

            perfis.append(perfis_item)

        personalizados = []
        _personalizados = d.pop("personalizados")
        for personalizados_item_data in _personalizados:
            personalizados_item = Papel.from_dict(personalizados_item_data)

            personalizados.append(personalizados_item)

        papeis = cls(
            perfis=perfis,
            personalizados=personalizados,
        )

        papeis.additional_properties = d
        return papeis

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
