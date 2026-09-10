from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.provedor_ldap_entrada_mapa_grupo_perfil import ProvedorLdapEntradaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorLdapEntrada")


@_attrs_define
class ProvedorLdapEntrada:
    """
    Attributes:
        habilitado (bool | Unset):  Default: True.
        url (None | str | Unset):
        base_dn (None | str | Unset):
        start_tls (bool | Unset):  Default: True.
        bind_dn (None | str | Unset):
        bind_senha (None | str | Unset):
        filtro_usuario (str | Unset):  Default: '(uid={login})'.
        atributo_grupos (str | Unset):  Default: 'memberOf'.
        perfil_padrao (None | str | Unset):
        mapa_grupo_perfil (ProvedorLdapEntradaMapaGrupoPerfil | Unset):
    """

    habilitado: bool | Unset = True
    url: None | str | Unset = UNSET
    base_dn: None | str | Unset = UNSET
    start_tls: bool | Unset = True
    bind_dn: None | str | Unset = UNSET
    bind_senha: None | str | Unset = UNSET
    filtro_usuario: str | Unset = "(uid={login})"
    atributo_grupos: str | Unset = "memberOf"
    perfil_padrao: None | str | Unset = UNSET
    mapa_grupo_perfil: ProvedorLdapEntradaMapaGrupoPerfil | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        habilitado = self.habilitado

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        base_dn: None | str | Unset
        if isinstance(self.base_dn, Unset):
            base_dn = UNSET
        else:
            base_dn = self.base_dn

        start_tls = self.start_tls

        bind_dn: None | str | Unset
        if isinstance(self.bind_dn, Unset):
            bind_dn = UNSET
        else:
            bind_dn = self.bind_dn

        bind_senha: None | str | Unset
        if isinstance(self.bind_senha, Unset):
            bind_senha = UNSET
        else:
            bind_senha = self.bind_senha

        filtro_usuario = self.filtro_usuario

        atributo_grupos = self.atributo_grupos

        perfil_padrao: None | str | Unset
        if isinstance(self.perfil_padrao, Unset):
            perfil_padrao = UNSET
        else:
            perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if habilitado is not UNSET:
            field_dict["habilitado"] = habilitado
        if url is not UNSET:
            field_dict["url"] = url
        if base_dn is not UNSET:
            field_dict["base_dn"] = base_dn
        if start_tls is not UNSET:
            field_dict["start_tls"] = start_tls
        if bind_dn is not UNSET:
            field_dict["bind_dn"] = bind_dn
        if bind_senha is not UNSET:
            field_dict["bind_senha"] = bind_senha
        if filtro_usuario is not UNSET:
            field_dict["filtro_usuario"] = filtro_usuario
        if atributo_grupos is not UNSET:
            field_dict["atributo_grupos"] = atributo_grupos
        if perfil_padrao is not UNSET:
            field_dict["perfil_padrao"] = perfil_padrao
        if mapa_grupo_perfil is not UNSET:
            field_dict["mapa_grupo_perfil"] = mapa_grupo_perfil

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_ldap_entrada_mapa_grupo_perfil import ProvedorLdapEntradaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        habilitado = d.pop("habilitado", UNSET)

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        def _parse_base_dn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        base_dn = _parse_base_dn(d.pop("base_dn", UNSET))

        start_tls = d.pop("start_tls", UNSET)

        def _parse_bind_dn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bind_dn = _parse_bind_dn(d.pop("bind_dn", UNSET))

        def _parse_bind_senha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bind_senha = _parse_bind_senha(d.pop("bind_senha", UNSET))

        filtro_usuario = d.pop("filtro_usuario", UNSET)

        atributo_grupos = d.pop("atributo_grupos", UNSET)

        def _parse_perfil_padrao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao", UNSET))

        _mapa_grupo_perfil = d.pop("mapa_grupo_perfil", UNSET)
        mapa_grupo_perfil: ProvedorLdapEntradaMapaGrupoPerfil | Unset
        if isinstance(_mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = UNSET
        else:
            mapa_grupo_perfil = ProvedorLdapEntradaMapaGrupoPerfil.from_dict(_mapa_grupo_perfil)

        provedor_ldap_entrada = cls(
            habilitado=habilitado,
            url=url,
            base_dn=base_dn,
            start_tls=start_tls,
            bind_dn=bind_dn,
            bind_senha=bind_senha,
            filtro_usuario=filtro_usuario,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        return provedor_ldap_entrada
