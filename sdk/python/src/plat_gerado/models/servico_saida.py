from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ServicoSaida")


@_attrs_define
class ServicoSaida:
    """
    Attributes:
        tipo (str):
        url (str):
        url_declarada (str):
        protocolo (str):
        camada (None | str | Unset):
    """

    tipo: str
    url: str
    url_declarada: str
    protocolo: str
    camada: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        url = self.url

        url_declarada = self.url_declarada

        protocolo = self.protocolo

        camada: None | str | Unset
        if isinstance(self.camada, Unset):
            camada = UNSET
        else:
            camada = self.camada

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo": tipo,
                "url": url,
                "url_declarada": url_declarada,
                "protocolo": protocolo,
            }
        )
        if camada is not UNSET:
            field_dict["camada"] = camada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo")

        url = d.pop("url")

        url_declarada = d.pop("url_declarada")

        protocolo = d.pop("protocolo")

        def _parse_camada(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        camada = _parse_camada(d.pop("camada", UNSET))

        servico_saida = cls(
            tipo=tipo,
            url=url,
            url_declarada=url_declarada,
            protocolo=protocolo,
            camada=camada,
        )

        servico_saida.additional_properties = d
        return servico_saida

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
