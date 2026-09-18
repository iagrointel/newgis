from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CampoSaida")


@_attrs_define
class CampoSaida:
    """
    Attributes:
        nome (str):
        origem (str):
        tipo (str):
        tipo_declarado (str):
        origem_do_tipo (str):
    """

    nome: str
    origem: str
    tipo: str
    tipo_declarado: str
    origem_do_tipo: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        origem = self.origem

        tipo = self.tipo

        tipo_declarado = self.tipo_declarado

        origem_do_tipo = self.origem_do_tipo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "origem": origem,
                "tipo": tipo,
                "tipo_declarado": tipo_declarado,
                "origem_do_tipo": origem_do_tipo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        origem = d.pop("origem")

        tipo = d.pop("tipo")

        tipo_declarado = d.pop("tipo_declarado")

        origem_do_tipo = d.pop("origem_do_tipo")

        campo_saida = cls(
            nome=nome,
            origem=origem,
            tipo=tipo,
            tipo_declarado=tipo_declarado,
            origem_do_tipo=origem_do_tipo,
        )

        campo_saida.additional_properties = d
        return campo_saida

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
