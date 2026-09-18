from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PresetImportado")


@_attrs_define
class PresetImportado:
    """
    Attributes:
        id (str):
        nome (str):
        escopo (str):
        integrado (bool | Unset):  Default: False.
        faltando (list[str] | Unset):
    """

    id: str
    nome: str
    escopo: str
    integrado: bool | Unset = False
    faltando: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        escopo = self.escopo

        integrado = self.integrado

        faltando: list[str] | Unset = UNSET
        if not isinstance(self.faltando, Unset):
            faltando = self.faltando

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "escopo": escopo,
            }
        )
        if integrado is not UNSET:
            field_dict["integrado"] = integrado
        if faltando is not UNSET:
            field_dict["faltando"] = faltando

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        escopo = d.pop("escopo")

        integrado = d.pop("integrado", UNSET)

        faltando = cast(list[str], d.pop("faltando", UNSET))

        preset_importado = cls(
            id=id,
            nome=nome,
            escopo=escopo,
            integrado=integrado,
            faltando=faltando,
        )

        preset_importado.additional_properties = d
        return preset_importado

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
