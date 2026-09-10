from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.compartilhamento_dependencias_item import CompartilhamentoDependenciasItem
    from ..models.compartilhamento_grupos_item import CompartilhamentoGruposItem
    from ..models.compartilhamento_links_item import CompartilhamentoLinksItem


T = TypeVar("T", bound="Compartilhamento")


@_attrs_define
class Compartilhamento:
    """
    Attributes:
        acesso (str):
        grupos (list[CompartilhamentoGruposItem]):
        links (list[CompartilhamentoLinksItem]):
        publico_permitido (bool):
        dependencias (list[CompartilhamentoDependenciasItem]):
    """

    acesso: str
    grupos: list[CompartilhamentoGruposItem]
    links: list[CompartilhamentoLinksItem]
    publico_permitido: bool
    dependencias: list[CompartilhamentoDependenciasItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        acesso = self.acesso

        grupos = []
        for grupos_item_data in self.grupos:
            grupos_item = grupos_item_data.to_dict()
            grupos.append(grupos_item)

        links = []
        for links_item_data in self.links:
            links_item = links_item_data.to_dict()
            links.append(links_item)

        publico_permitido = self.publico_permitido

        dependencias = []
        for dependencias_item_data in self.dependencias:
            dependencias_item = dependencias_item_data.to_dict()
            dependencias.append(dependencias_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "acesso": acesso,
                "grupos": grupos,
                "links": links,
                "publico_permitido": publico_permitido,
                "dependencias": dependencias,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.compartilhamento_dependencias_item import CompartilhamentoDependenciasItem  # noqa: PLC0415
        from ..models.compartilhamento_grupos_item import CompartilhamentoGruposItem  # noqa: PLC0415
        from ..models.compartilhamento_links_item import CompartilhamentoLinksItem  # noqa: PLC0415

        d = dict(src_dict)
        acesso = d.pop("acesso")

        grupos = []
        _grupos = d.pop("grupos")
        for grupos_item_data in _grupos:
            grupos_item = CompartilhamentoGruposItem.from_dict(grupos_item_data)

            grupos.append(grupos_item)

        links = []
        _links = d.pop("links")
        for links_item_data in _links:
            links_item = CompartilhamentoLinksItem.from_dict(links_item_data)

            links.append(links_item)

        publico_permitido = d.pop("publico_permitido")

        dependencias = []
        _dependencias = d.pop("dependencias")
        for dependencias_item_data in _dependencias:
            dependencias_item = CompartilhamentoDependenciasItem.from_dict(dependencias_item_data)

            dependencias.append(dependencias_item)

        compartilhamento = cls(
            acesso=acesso,
            grupos=grupos,
            links=links,
            publico_permitido=publico_permitido,
            dependencias=dependencias,
        )

        compartilhamento.additional_properties = d
        return compartilhamento

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
