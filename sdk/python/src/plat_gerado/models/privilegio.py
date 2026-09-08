from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Privilegio")


@_attrs_define
class Privilegio:
    """
    Attributes:
        nome (str):
        grupo (str):
        descricao (str):
        administrativo (bool):
    """

    nome: str
    grupo: str
    descricao: str
    administrativo: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        grupo = self.grupo

        descricao = self.descricao

        administrativo = self.administrativo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "grupo": grupo,
                "descricao": descricao,
                "administrativo": administrativo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        grupo = d.pop("grupo")

        descricao = d.pop("descricao")

        administrativo = d.pop("administrativo")

        privilegio = cls(
            nome=nome,
            grupo=grupo,
            descricao=descricao,
            administrativo=administrativo,
        )

        privilegio.additional_properties = d
        return privilegio

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
