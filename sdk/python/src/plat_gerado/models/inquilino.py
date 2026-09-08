from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Inquilino")


@_attrs_define
class Inquilino:
    """
    Attributes:
        id (int):
        slug (str):
        nome (str):
        ativo (bool):
        usuarios (int):
        criado_em (None | str):
        ultimo_acesso (None | str):
    """

    id: int
    slug: str
    nome: str
    ativo: bool
    usuarios: int
    criado_em: None | str
    ultimo_acesso: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        slug = self.slug

        nome = self.nome

        ativo = self.ativo

        usuarios = self.usuarios

        criado_em: None | str
        criado_em = self.criado_em

        ultimo_acesso: None | str
        ultimo_acesso = self.ultimo_acesso

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "slug": slug,
                "nome": nome,
                "ativo": ativo,
                "usuarios": usuarios,
                "criado_em": criado_em,
                "ultimo_acesso": ultimo_acesso,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        slug = d.pop("slug")

        nome = d.pop("nome")

        ativo = d.pop("ativo")

        usuarios = d.pop("usuarios")

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        def _parse_ultimo_acesso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ultimo_acesso = _parse_ultimo_acesso(d.pop("ultimo_acesso"))

        inquilino = cls(
            id=id,
            slug=slug,
            nome=nome,
            ativo=ativo,
            usuarios=usuarios,
            criado_em=criado_em,
            ultimo_acesso=ultimo_acesso,
        )

        inquilino.additional_properties = d
        return inquilino

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
