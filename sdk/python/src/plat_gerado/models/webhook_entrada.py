from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="WebhookEntrada")


@_attrs_define
class WebhookEntrada:
    """
    Attributes:
        nome (str):
        url (str):
        eventos (list[str]):
    """

    nome: str
    url: str
    eventos: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        url = self.url

        eventos = self.eventos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "url": url,
                "eventos": eventos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        url = d.pop("url")

        eventos = cast(list[str], d.pop("eventos"))

        webhook_entrada = cls(
            nome=nome,
            url=url,
            eventos=eventos,
        )

        webhook_entrada.additional_properties = d
        return webhook_entrada

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
