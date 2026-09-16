from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SubstituicaoEntrada")


@_attrs_define
class SubstituicaoEntrada:
    """
    Attributes:
        tipo_id (str):
        atributo_codigo (str):
        de_valor (int):
        para_valor (int):
        descricao (None | str | Unset):
    """

    tipo_id: str
    atributo_codigo: str
    de_valor: int
    para_valor: int
    descricao: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_id = self.tipo_id

        atributo_codigo = self.atributo_codigo

        de_valor = self.de_valor

        para_valor = self.para_valor

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo_id": tipo_id,
                "atributo_codigo": atributo_codigo,
                "de_valor": de_valor,
                "para_valor": para_valor,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo_id = d.pop("tipo_id")

        atributo_codigo = d.pop("atributo_codigo")

        de_valor = d.pop("de_valor")

        para_valor = d.pop("para_valor")

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        substituicao_entrada = cls(
            tipo_id=tipo_id,
            atributo_codigo=atributo_codigo,
            de_valor=de_valor,
            para_valor=para_valor,
            descricao=descricao,
        )

        substituicao_entrada.additional_properties = d
        return substituicao_entrada

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
