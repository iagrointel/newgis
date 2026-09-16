from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AtributoRede")


@_attrs_define
class AtributoRede:
    """Atributo DE REDE: um campo da camada de origem que o inquilino declara como parte do modelo de rede
    (é o que o traçado pode usar como custo em `caminho_curto`). Declarar é o que separa um campo qualquer
    da camada de um atributo de rede.

        Attributes:
            nome (str):
            tipo_dado (str | Unset):  Default: 'texto'.
            de (str | Unset):  Default: 'linha'.
    """

    nome: str
    tipo_dado: str | Unset = "texto"
    de: str | Unset = "linha"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        tipo_dado = self.tipo_dado

        de = self.de

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
            }
        )
        if tipo_dado is not UNSET:
            field_dict["tipo_dado"] = tipo_dado
        if de is not UNSET:
            field_dict["de"] = de

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        tipo_dado = d.pop("tipo_dado", UNSET)

        de = d.pop("de", UNSET)

        atributo_rede = cls(
            nome=nome,
            tipo_dado=tipo_dado,
            de=de,
        )

        atributo_rede.additional_properties = d
        return atributo_rede

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
