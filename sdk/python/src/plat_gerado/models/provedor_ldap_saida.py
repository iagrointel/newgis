from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.provedor_ldap_saida_mapa_grupo_perfil import ProvedorLdapSaidaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorLdapSaida")


@_attrs_define
class ProvedorLdapSaida:
    """
    Attributes:
        habilitado (bool):
        url (None | str):
        base_dn (None | str):
        start_tls (bool):
        bind_dn (None | str):
        tem_bind_senha (bool):
        filtro_usuario (str):
        atributo_grupos (str):
        perfil_padrao (None | str):
        mapa_grupo_perfil (ProvedorLdapSaidaMapaGrupoPerfil):
    """

    habilitado: bool
    url: None | str
    base_dn: None | str
    start_tls: bool
    bind_dn: None | str
    tem_bind_senha: bool
    filtro_usuario: str
    atributo_grupos: str
    perfil_padrao: None | str
    mapa_grupo_perfil: ProvedorLdapSaidaMapaGrupoPerfil
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        habilitado = self.habilitado

        url: None | str
        url = self.url

        base_dn: None | str
        base_dn = self.base_dn

        start_tls = self.start_tls

        bind_dn: None | str
        bind_dn = self.bind_dn

        tem_bind_senha = self.tem_bind_senha

        filtro_usuario = self.filtro_usuario

        atributo_grupos = self.atributo_grupos

        perfil_padrao: None | str
        perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "habilitado": habilitado,
                "url": url,
                "base_dn": base_dn,
                "start_tls": start_tls,
                "bind_dn": bind_dn,
                "tem_bind_senha": tem_bind_senha,
                "filtro_usuario": filtro_usuario,
                "atributo_grupos": atributo_grupos,
                "perfil_padrao": perfil_padrao,
                "mapa_grupo_perfil": mapa_grupo_perfil,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_ldap_saida_mapa_grupo_perfil import ProvedorLdapSaidaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        habilitado = d.pop("habilitado")

        def _parse_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        url = _parse_url(d.pop("url"))

        def _parse_base_dn(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        base_dn = _parse_base_dn(d.pop("base_dn"))

        start_tls = d.pop("start_tls")

        def _parse_bind_dn(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        bind_dn = _parse_bind_dn(d.pop("bind_dn"))

        tem_bind_senha = d.pop("tem_bind_senha")

        filtro_usuario = d.pop("filtro_usuario")

        atributo_grupos = d.pop("atributo_grupos")

        def _parse_perfil_padrao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao"))

        mapa_grupo_perfil = ProvedorLdapSaidaMapaGrupoPerfil.from_dict(d.pop("mapa_grupo_perfil"))

        provedor_ldap_saida = cls(
            habilitado=habilitado,
            url=url,
            base_dn=base_dn,
            start_tls=start_tls,
            bind_dn=bind_dn,
            tem_bind_senha=tem_bind_senha,
            filtro_usuario=filtro_usuario,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        provedor_ldap_saida.additional_properties = d
        return provedor_ldap_saida

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
