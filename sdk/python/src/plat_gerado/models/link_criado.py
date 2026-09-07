from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="LinkCriado")


@_attrs_define
class LinkCriado:
    """
    Attributes:
        id (str):
        prefixo (str):
        nome (None | str):
        criado_em (None | str):
        expira_em (None | str):
        revogado_em (None | str):
        acessos (int):
        itens_incluidos (list[str]):
        token (str):
        url (str):
    """

    id: str
    prefixo: str
    nome: None | str
    criado_em: None | str
    expira_em: None | str
    revogado_em: None | str
    acessos: int
    itens_incluidos: list[str]
    token: str
    url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        prefixo = self.prefixo

        nome: None | str
        nome = self.nome

        criado_em: None | str
        criado_em = self.criado_em

        expira_em: None | str
        expira_em = self.expira_em

        revogado_em: None | str
        revogado_em = self.revogado_em

        acessos = self.acessos

        itens_incluidos = self.itens_incluidos

        token = self.token

        url = self.url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "prefixo": prefixo,
                "nome": nome,
                "criado_em": criado_em,
                "expira_em": expira_em,
                "revogado_em": revogado_em,
                "acessos": acessos,
                "itens_incluidos": itens_incluidos,
                "token": token,
                "url": url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        prefixo = d.pop("prefixo")

        def _parse_nome(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        nome = _parse_nome(d.pop("nome"))

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        def _parse_expira_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        expira_em = _parse_expira_em(d.pop("expira_em"))

        def _parse_revogado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        revogado_em = _parse_revogado_em(d.pop("revogado_em"))

        acessos = d.pop("acessos")

        itens_incluidos = cast(list[str], d.pop("itens_incluidos"))

        token = d.pop("token")

        url = d.pop("url")

        link_criado = cls(
            id=id,
            prefixo=prefixo,
            nome=nome,
            criado_em=criado_em,
            expira_em=expira_em,
            revogado_em=revogado_em,
            acessos=acessos,
            itens_incluidos=itens_incluidos,
            token=token,
            url=url,
        )

        link_criado.additional_properties = d
        return link_criado

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
