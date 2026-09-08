from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TokenCriado")


@_attrs_define
class TokenCriado:
    """
    Attributes:
        token (str):
        id (int):
        prefixo (str):
        escopos (list[str]):
        expira_em (None | str):
        antigo_expira_em (None | str | Unset):
    """

    token: str
    id: int
    prefixo: str
    escopos: list[str]
    expira_em: None | str
    antigo_expira_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        id = self.id

        prefixo = self.prefixo

        escopos = self.escopos

        expira_em: None | str
        expira_em = self.expira_em

        antigo_expira_em: None | str | Unset
        if isinstance(self.antigo_expira_em, Unset):
            antigo_expira_em = UNSET
        else:
            antigo_expira_em = self.antigo_expira_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token": token,
                "id": id,
                "prefixo": prefixo,
                "escopos": escopos,
                "expira_em": expira_em,
            }
        )
        if antigo_expira_em is not UNSET:
            field_dict["antigo_expira_em"] = antigo_expira_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        id = d.pop("id")

        prefixo = d.pop("prefixo")

        escopos = cast(list[str], d.pop("escopos"))

        def _parse_expira_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        expira_em = _parse_expira_em(d.pop("expira_em"))

        def _parse_antigo_expira_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        antigo_expira_em = _parse_antigo_expira_em(d.pop("antigo_expira_em", UNSET))

        token_criado = cls(
            token=token,
            id=id,
            prefixo=prefixo,
            escopos=escopos,
            expira_em=expira_em,
            antigo_expira_em=antigo_expira_em,
        )

        token_criado.additional_properties = d
        return token_criado

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
