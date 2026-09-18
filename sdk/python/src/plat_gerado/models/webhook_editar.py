from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="WebhookEditar")


@_attrs_define
class WebhookEditar:
    """
    Attributes:
        nome (None | str | Unset):
        url (None | str | Unset):
        eventos (list[str] | None | Unset):
    """

    nome: None | str | Unset = UNSET
    url: None | str | Unset = UNSET
    eventos: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        eventos: list[str] | None | Unset
        if isinstance(self.eventos, Unset):
            eventos = UNSET
        elif isinstance(self.eventos, list):
            eventos = self.eventos

        else:
            eventos = self.eventos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if url is not UNSET:
            field_dict["url"] = url
        if eventos is not UNSET:
            field_dict["eventos"] = eventos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        def _parse_eventos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                eventos_type_0 = cast(list[str], data)

                return eventos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        eventos = _parse_eventos(d.pop("eventos", UNSET))

        webhook_editar = cls(
            nome=nome,
            url=url,
            eventos=eventos,
        )

        webhook_editar.additional_properties = d
        return webhook_editar

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
