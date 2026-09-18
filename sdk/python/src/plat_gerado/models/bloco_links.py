from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.link_org import LinkOrg


T = TypeVar("T", bound="BlocoLinks")


@_attrs_define
class BlocoLinks:
    """
    Attributes:
        tipo (Literal['links']):
        links (list[LinkOrg]):
        titulo (str | Unset):  Default: ''.
    """

    tipo: Literal["links"]
    links: list[LinkOrg]
    titulo: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        links = []
        for links_item_data in self.links:
            links_item = links_item_data.to_dict()
            links.append(links_item)

        titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "links": links,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.link_org import LinkOrg  # noqa: PLC0415

        d = dict(src_dict)
        tipo = cast(Literal["links"], d.pop("tipo"))
        if tipo != "links":
            raise ValueError(f"tipo must match const 'links', got '{tipo}'")

        links = []
        _links = d.pop("links")
        for links_item_data in _links:
            links_item = LinkOrg.from_dict(links_item_data)

            links.append(links_item)

        titulo = d.pop("titulo", UNSET)

        bloco_links = cls(
            tipo=tipo,
            links=links,
            titulo=titulo,
        )

        return bloco_links
