from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.provedor_oidc_entrada_mapa_grupo_perfil import ProvedorOidcEntradaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorOidcEntrada")


@_attrs_define
class ProvedorOidcEntrada:
    """
    Attributes:
        issuer (str):
        client_id (str):
        habilitado (bool | Unset):  Default: True.
        rotulo (str | Unset):  Default: 'Entrar com a organização'.
        ordem (int | Unset):  Default: 0.
        client_secret (None | str | Unset):
        escopos (str | Unset):  Default: 'openid profile email'.
        atributo_grupos (str | Unset):  Default: 'groups'.
        perfil_padrao (None | str | Unset):
        mapa_grupo_perfil (ProvedorOidcEntradaMapaGrupoPerfil | Unset):
        modelo (str | Unset):  Default: 'generico'.
        api_base (None | str | Unset):
    """

    issuer: str
    client_id: str
    habilitado: bool | Unset = True
    rotulo: str | Unset = "Entrar com a organização"
    ordem: int | Unset = 0
    client_secret: None | str | Unset = UNSET
    escopos: str | Unset = "openid profile email"
    atributo_grupos: str | Unset = "groups"
    perfil_padrao: None | str | Unset = UNSET
    mapa_grupo_perfil: ProvedorOidcEntradaMapaGrupoPerfil | Unset = UNSET
    modelo: str | Unset = "generico"
    api_base: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        issuer = self.issuer

        client_id = self.client_id

        habilitado = self.habilitado

        rotulo = self.rotulo

        ordem = self.ordem

        client_secret: None | str | Unset
        if isinstance(self.client_secret, Unset):
            client_secret = UNSET
        else:
            client_secret = self.client_secret

        escopos = self.escopos

        atributo_grupos = self.atributo_grupos

        perfil_padrao: None | str | Unset
        if isinstance(self.perfil_padrao, Unset):
            perfil_padrao = UNSET
        else:
            perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        modelo = self.modelo

        api_base: None | str | Unset
        if isinstance(self.api_base, Unset):
            api_base = UNSET
        else:
            api_base = self.api_base

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "issuer": issuer,
                "client_id": client_id,
            }
        )
        if habilitado is not UNSET:
            field_dict["habilitado"] = habilitado
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if client_secret is not UNSET:
            field_dict["client_secret"] = client_secret
        if escopos is not UNSET:
            field_dict["escopos"] = escopos
        if atributo_grupos is not UNSET:
            field_dict["atributo_grupos"] = atributo_grupos
        if perfil_padrao is not UNSET:
            field_dict["perfil_padrao"] = perfil_padrao
        if mapa_grupo_perfil is not UNSET:
            field_dict["mapa_grupo_perfil"] = mapa_grupo_perfil
        if modelo is not UNSET:
            field_dict["modelo"] = modelo
        if api_base is not UNSET:
            field_dict["api_base"] = api_base

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_oidc_entrada_mapa_grupo_perfil import ProvedorOidcEntradaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        issuer = d.pop("issuer")

        client_id = d.pop("client_id")

        habilitado = d.pop("habilitado", UNSET)

        rotulo = d.pop("rotulo", UNSET)

        ordem = d.pop("ordem", UNSET)

        def _parse_client_secret(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        client_secret = _parse_client_secret(d.pop("client_secret", UNSET))

        escopos = d.pop("escopos", UNSET)

        atributo_grupos = d.pop("atributo_grupos", UNSET)

        def _parse_perfil_padrao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao", UNSET))

        _mapa_grupo_perfil = d.pop("mapa_grupo_perfil", UNSET)
        mapa_grupo_perfil: ProvedorOidcEntradaMapaGrupoPerfil | Unset
        if isinstance(_mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = UNSET
        else:
            mapa_grupo_perfil = ProvedorOidcEntradaMapaGrupoPerfil.from_dict(_mapa_grupo_perfil)

        modelo = d.pop("modelo", UNSET)

        def _parse_api_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        api_base = _parse_api_base(d.pop("api_base", UNSET))

        provedor_oidc_entrada = cls(
            issuer=issuer,
            client_id=client_id,
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            client_secret=client_secret,
            escopos=escopos,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
            modelo=modelo,
            api_base=api_base,
        )

        return provedor_oidc_entrada
