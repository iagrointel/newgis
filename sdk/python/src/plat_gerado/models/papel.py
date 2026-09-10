from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Papel")


@_attrs_define
class Papel:
    """
    Attributes:
        id (int):
        nome (str):
        descricao (None | str):
        perfil_minimo (str):
        privilegios (list[str]):
        usuarios (int):
        criado_em (None | str | Unset):
    """

    id: int
    nome: str
    descricao: None | str
    perfil_minimo: str
    privilegios: list[str]
    usuarios: int
    criado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nome = self.nome

        descricao: None | str
        descricao = self.descricao

        perfil_minimo = self.perfil_minimo

        privilegios = self.privilegios

        usuarios = self.usuarios

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nome": nome,
                "descricao": descricao,
                "perfil_minimo": perfil_minimo,
                "privilegios": privilegios,
                "usuarios": usuarios,
            }
        )
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nome = d.pop("nome")

        def _parse_descricao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        descricao = _parse_descricao(d.pop("descricao"))

        perfil_minimo = d.pop("perfil_minimo")

        privilegios = cast(list[str], d.pop("privilegios"))

        usuarios = d.pop("usuarios")

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        papel = cls(
            id=id,
            nome=nome,
            descricao=descricao,
            perfil_minimo=perfil_minimo,
            privilegios=privilegios,
            usuarios=usuarios,
            criado_em=criado_em,
        )

        papel.additional_properties = d
        return papel

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
