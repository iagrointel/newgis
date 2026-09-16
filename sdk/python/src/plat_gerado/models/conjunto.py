from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Conjunto")


@_attrs_define
class Conjunto:
    """
    Attributes:
        id (str):
        nome (str):
        srid_trabalho (int):
        srid_nome (str):
        origem_x_m (float):
        origem_y_m (float):
        largura_m (float):
        altura_m (float):
        criado_em (str):
    """

    id: str
    nome: str
    srid_trabalho: int
    srid_nome: str
    origem_x_m: float
    origem_y_m: float
    largura_m: float
    altura_m: float
    criado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        srid_trabalho = self.srid_trabalho

        srid_nome = self.srid_nome

        origem_x_m = self.origem_x_m

        origem_y_m = self.origem_y_m

        largura_m = self.largura_m

        altura_m = self.altura_m

        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "srid_trabalho": srid_trabalho,
                "srid_nome": srid_nome,
                "origem_x_m": origem_x_m,
                "origem_y_m": origem_y_m,
                "largura_m": largura_m,
                "altura_m": altura_m,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        srid_trabalho = d.pop("srid_trabalho")

        srid_nome = d.pop("srid_nome")

        origem_x_m = d.pop("origem_x_m")

        origem_y_m = d.pop("origem_y_m")

        largura_m = d.pop("largura_m")

        altura_m = d.pop("altura_m")

        criado_em = d.pop("criado_em")

        conjunto = cls(
            id=id,
            nome=nome,
            srid_trabalho=srid_trabalho,
            srid_nome=srid_nome,
            origem_x_m=origem_x_m,
            origem_y_m=origem_y_m,
            largura_m=largura_m,
            altura_m=altura_m,
            criado_em=criado_em,
        )

        conjunto.additional_properties = d
        return conjunto

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
