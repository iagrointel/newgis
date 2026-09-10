from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConviteResolvido")


@_attrs_define
class ConviteResolvido:
    """
    Attributes:
        motivo (str):
        tenant_nome (None | str | Unset):
        email (None | str | Unset):
        perfil (None | str | Unset):
        expira_em (None | str | Unset):
    """

    motivo: str
    tenant_nome: None | str | Unset = UNSET
    email: None | str | Unset = UNSET
    perfil: None | str | Unset = UNSET
    expira_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        motivo = self.motivo

        tenant_nome: None | str | Unset
        if isinstance(self.tenant_nome, Unset):
            tenant_nome = UNSET
        else:
            tenant_nome = self.tenant_nome

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        perfil: None | str | Unset
        if isinstance(self.perfil, Unset):
            perfil = UNSET
        else:
            perfil = self.perfil

        expira_em: None | str | Unset
        if isinstance(self.expira_em, Unset):
            expira_em = UNSET
        else:
            expira_em = self.expira_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "motivo": motivo,
            }
        )
        if tenant_nome is not UNSET:
            field_dict["tenant_nome"] = tenant_nome
        if email is not UNSET:
            field_dict["email"] = email
        if perfil is not UNSET:
            field_dict["perfil"] = perfil
        if expira_em is not UNSET:
            field_dict["expira_em"] = expira_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        motivo = d.pop("motivo")

        def _parse_tenant_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tenant_nome = _parse_tenant_nome(d.pop("tenant_nome", UNSET))

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_perfil(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil = _parse_perfil(d.pop("perfil", UNSET))

        def _parse_expira_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expira_em = _parse_expira_em(d.pop("expira_em", UNSET))

        convite_resolvido = cls(
            motivo=motivo,
            tenant_nome=tenant_nome,
            email=email,
            perfil=perfil,
            expira_em=expira_em,
        )

        convite_resolvido.additional_properties = d
        return convite_resolvido

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
