from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.login_provedor import LoginProvedor
    from ..models.logins_govbr import LoginsGovbr


T = TypeVar("T", bound="Logins")


@_attrs_define
class Logins:
    """
    Attributes:
        provedores (list[LoginProvedor]):
        criacoes (list[str]):
        perfis (list[str]):
        redirect_uri_oidc (str):
        govbr (LoginsGovbr):
    """

    provedores: list[LoginProvedor]
    criacoes: list[str]
    perfis: list[str]
    redirect_uri_oidc: str
    govbr: LoginsGovbr
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        provedores = []
        for provedores_item_data in self.provedores:
            provedores_item = provedores_item_data.to_dict()
            provedores.append(provedores_item)

        criacoes = self.criacoes

        perfis = self.perfis

        redirect_uri_oidc = self.redirect_uri_oidc

        govbr = self.govbr.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "provedores": provedores,
                "criacoes": criacoes,
                "perfis": perfis,
                "redirect_uri_oidc": redirect_uri_oidc,
                "govbr": govbr,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.login_provedor import LoginProvedor  # noqa: PLC0415
        from ..models.logins_govbr import LoginsGovbr  # noqa: PLC0415

        d = dict(src_dict)
        provedores = []
        _provedores = d.pop("provedores")
        for provedores_item_data in _provedores:
            provedores_item = LoginProvedor.from_dict(provedores_item_data)

            provedores.append(provedores_item)

        criacoes = cast(list[str], d.pop("criacoes"))

        perfis = cast(list[str], d.pop("perfis"))

        redirect_uri_oidc = d.pop("redirect_uri_oidc")

        govbr = LoginsGovbr.from_dict(d.pop("govbr"))

        logins = cls(
            provedores=provedores,
            criacoes=criacoes,
            perfis=perfis,
            redirect_uri_oidc=redirect_uri_oidc,
            govbr=govbr,
        )

        logins.additional_properties = d
        return logins

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
