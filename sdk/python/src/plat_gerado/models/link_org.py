from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="LinkOrg")


@_attrs_define
class LinkOrg:
    """
    Attributes:
        rotulo (str):
        url (str):
    """

    rotulo: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        rotulo = self.rotulo

        url = self.url

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "rotulo": rotulo,
                "url": url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rotulo = d.pop("rotulo")

        url = d.pop("url")

        link_org = cls(
            rotulo=rotulo,
            url=url,
        )

        return link_org
