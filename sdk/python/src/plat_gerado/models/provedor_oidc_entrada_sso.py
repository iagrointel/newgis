from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.provedor_oidc_entrada_sso_mapa_grupo_perfil import ProvedorOidcEntradaSsoMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorOidcEntradaSso")


@_attrs_define
class ProvedorOidcEntradaSso:
    """
    Attributes:
        emissor (str):
        cliente_id (str):
        habilitado (bool | Unset):  Default: True.
        cliente_segredo (None | str | Unset):
        claim_grupos (str | Unset):  Default: 'groups'.
        claim_login (None | str | Unset):
        perfil_padrao (None | str | Unset):
        mapa_grupo_perfil (ProvedorOidcEntradaSsoMapaGrupoPerfil | Unset):
    """

    emissor: str
    cliente_id: str
    habilitado: bool | Unset = True
    cliente_segredo: None | str | Unset = UNSET
    claim_grupos: str | Unset = "groups"
    claim_login: None | str | Unset = UNSET
    perfil_padrao: None | str | Unset = UNSET
    mapa_grupo_perfil: ProvedorOidcEntradaSsoMapaGrupoPerfil | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        emissor = self.emissor

        cliente_id = self.cliente_id

        habilitado = self.habilitado

        cliente_segredo: None | str | Unset
        if isinstance(self.cliente_segredo, Unset):
            cliente_segredo = UNSET
        else:
            cliente_segredo = self.cliente_segredo

        claim_grupos = self.claim_grupos

        claim_login: None | str | Unset
        if isinstance(self.claim_login, Unset):
            claim_login = UNSET
        else:
            claim_login = self.claim_login

        perfil_padrao: None | str | Unset
        if isinstance(self.perfil_padrao, Unset):
            perfil_padrao = UNSET
        else:
            perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "emissor": emissor,
                "cliente_id": cliente_id,
            }
        )
        if habilitado is not UNSET:
            field_dict["habilitado"] = habilitado
        if cliente_segredo is not UNSET:
            field_dict["cliente_segredo"] = cliente_segredo
        if claim_grupos is not UNSET:
            field_dict["claim_grupos"] = claim_grupos
        if claim_login is not UNSET:
            field_dict["claim_login"] = claim_login
        if perfil_padrao is not UNSET:
            field_dict["perfil_padrao"] = perfil_padrao
        if mapa_grupo_perfil is not UNSET:
            field_dict["mapa_grupo_perfil"] = mapa_grupo_perfil

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_oidc_entrada_sso_mapa_grupo_perfil import (
            ProvedorOidcEntradaSsoMapaGrupoPerfil,  # noqa: PLC0415
        )

        d = dict(src_dict)
        emissor = d.pop("emissor")

        cliente_id = d.pop("cliente_id")

        habilitado = d.pop("habilitado", UNSET)

        def _parse_cliente_segredo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cliente_segredo = _parse_cliente_segredo(d.pop("cliente_segredo", UNSET))

        claim_grupos = d.pop("claim_grupos", UNSET)

        def _parse_claim_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        claim_login = _parse_claim_login(d.pop("claim_login", UNSET))

        def _parse_perfil_padrao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao", UNSET))

        _mapa_grupo_perfil = d.pop("mapa_grupo_perfil", UNSET)
        mapa_grupo_perfil: ProvedorOidcEntradaSsoMapaGrupoPerfil | Unset
        if isinstance(_mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = UNSET
        else:
            mapa_grupo_perfil = ProvedorOidcEntradaSsoMapaGrupoPerfil.from_dict(_mapa_grupo_perfil)

        provedor_oidc_entrada_sso = cls(
            emissor=emissor,
            cliente_id=cliente_id,
            habilitado=habilitado,
            cliente_segredo=cliente_segredo,
            claim_grupos=claim_grupos,
            claim_login=claim_login,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        return provedor_oidc_entrada_sso
