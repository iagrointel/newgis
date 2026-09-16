from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Publicacao")


@_attrs_define
class Publicacao:
    """
    Attributes:
        item_id (str):
        slug (str):
        url (str):
        dominios_permitidos (list[str]):
        token_id (int | None):
        publicado_em (None | str):
        atualizado_em (None | str):
        camadas_citadas (list[str]):
    """

    item_id: str
    slug: str
    url: str
    dominios_permitidos: list[str]
    token_id: int | None
    publicado_em: None | str
    atualizado_em: None | str
    camadas_citadas: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        slug = self.slug

        url = self.url

        dominios_permitidos = self.dominios_permitidos

        token_id: int | None
        token_id = self.token_id

        publicado_em: None | str
        publicado_em = self.publicado_em

        atualizado_em: None | str
        atualizado_em = self.atualizado_em

        camadas_citadas = self.camadas_citadas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "slug": slug,
                "url": url,
                "dominios_permitidos": dominios_permitidos,
                "token_id": token_id,
                "publicado_em": publicado_em,
                "atualizado_em": atualizado_em,
                "camadas_citadas": camadas_citadas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        slug = d.pop("slug")

        url = d.pop("url")

        dominios_permitidos = cast(list[str], d.pop("dominios_permitidos"))

        def _parse_token_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        token_id = _parse_token_id(d.pop("token_id"))

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

        camadas_citadas = cast(list[str], d.pop("camadas_citadas"))

        publicacao = cls(
            item_id=item_id,
            slug=slug,
            url=url,
            dominios_permitidos=dominios_permitidos,
            token_id=token_id,
            publicado_em=publicado_em,
            atualizado_em=atualizado_em,
            camadas_citadas=camadas_citadas,
        )

        publicacao.additional_properties = d
        return publicacao

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
