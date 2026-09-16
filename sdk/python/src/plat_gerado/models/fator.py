from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Fator")


@_attrs_define
class Fator:
    """
    Attributes:
        id (str):
        nome (str):
        resolucao_fonte_m (float):
        papel (str):
        unidade (str):
        fonte (str):
        criado_em (str):
    """

    id: str
    nome: str
    resolucao_fonte_m: float
    papel: str
    unidade: str
    fonte: str
    criado_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        resolucao_fonte_m = self.resolucao_fonte_m

        papel = self.papel

        unidade = self.unidade

        fonte = self.fonte

        criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "resolucao_fonte_m": resolucao_fonte_m,
                "papel": papel,
                "unidade": unidade,
                "fonte": fonte,
                "criado_em": criado_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        resolucao_fonte_m = d.pop("resolucao_fonte_m")

        papel = d.pop("papel")

        unidade = d.pop("unidade")

        fonte = d.pop("fonte")

        criado_em = d.pop("criado_em")

        fator = cls(
            id=id,
            nome=nome,
            resolucao_fonte_m=resolucao_fonte_m,
            papel=papel,
            unidade=unidade,
            fonte=fonte,
            criado_em=criado_em,
        )

        fator.additional_properties = d
        return fator

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
