from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Site")


@_attrs_define
class Site:
    """
    Attributes:
        item_id (str):
        tenant_slug (str):
        url (str):
        indexavel (bool):
        versao_publicada (int | None):
        publicado_em (None | str):
        atualizado_em (None | str):
    """

    item_id: str
    tenant_slug: str
    url: str
    indexavel: bool
    versao_publicada: int | None
    publicado_em: None | str
    atualizado_em: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        tenant_slug = self.tenant_slug

        url = self.url

        indexavel = self.indexavel

        versao_publicada: int | None
        versao_publicada = self.versao_publicada

        publicado_em: None | str
        publicado_em = self.publicado_em

        atualizado_em: None | str
        atualizado_em = self.atualizado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "tenant_slug": tenant_slug,
                "url": url,
                "indexavel": indexavel,
                "versao_publicada": versao_publicada,
                "publicado_em": publicado_em,
                "atualizado_em": atualizado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        tenant_slug = d.pop("tenant_slug")

        url = d.pop("url")

        indexavel = d.pop("indexavel")

        def _parse_versao_publicada(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        versao_publicada = _parse_versao_publicada(d.pop("versao_publicada"))

        def _parse_publicado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        publicado_em = _parse_publicado_em(d.pop("publicado_em"))

        def _parse_atualizado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        atualizado_em = _parse_atualizado_em(d.pop("atualizado_em"))

        site = cls(
            item_id=item_id,
            tenant_slug=tenant_slug,
            url=url,
            indexavel=indexavel,
            versao_publicada=versao_publicada,
            publicado_em=publicado_em,
            atualizado_em=atualizado_em,
        )

        site.additional_properties = d
        return site

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
