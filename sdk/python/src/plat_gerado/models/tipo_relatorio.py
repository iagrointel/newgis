from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TipoRelatorio")


@_attrs_define
class TipoRelatorio:
    """
    Attributes:
        tipo (str):
        descricao (str):
        cabecalho (list[str]):
    """

    tipo: str
    descricao: str
    cabecalho: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        descricao = self.descricao

        cabecalho = self.cabecalho

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo": tipo,
                "descricao": descricao,
                "cabecalho": cabecalho,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo")

        descricao = d.pop("descricao")

        cabecalho = cast(list[str], d.pop("cabecalho"))

        tipo_relatorio = cls(
            tipo=tipo,
            descricao=descricao,
            cabecalho=cabecalho,
        )

        tipo_relatorio.additional_properties = d
        return tipo_relatorio

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
