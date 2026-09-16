from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.provedor_oidc_saida_mapa_grupo_perfil import ProvedorOidcSaidaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorOidcSaida")


@_attrs_define
class ProvedorOidcSaida:
    """
    Attributes:
        id (int):
        habilitado (bool):
        rotulo (str):
        ordem (int):
        issuer (str):
        client_id (str):
        tem_client_secret (bool):
        escopos (str):
        atributo_grupos (str):
        perfil_padrao (None | str):
        mapa_grupo_perfil (ProvedorOidcSaidaMapaGrupoPerfil):
        modelo (str):
        api_base (None | str):
    """

    id: int
    habilitado: bool
    rotulo: str
    ordem: int
    issuer: str
    client_id: str
    tem_client_secret: bool
    escopos: str
    atributo_grupos: str
    perfil_padrao: None | str
    mapa_grupo_perfil: ProvedorOidcSaidaMapaGrupoPerfil
    modelo: str
    api_base: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        habilitado = self.habilitado

        rotulo = self.rotulo

        ordem = self.ordem

        issuer = self.issuer

        client_id = self.client_id

        tem_client_secret = self.tem_client_secret

        escopos = self.escopos

        atributo_grupos = self.atributo_grupos

        perfil_padrao: None | str
        perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        modelo = self.modelo

        api_base: None | str
        api_base = self.api_base

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "habilitado": habilitado,
                "rotulo": rotulo,
                "ordem": ordem,
                "issuer": issuer,
                "client_id": client_id,
                "tem_client_secret": tem_client_secret,
                "escopos": escopos,
                "atributo_grupos": atributo_grupos,
                "perfil_padrao": perfil_padrao,
                "mapa_grupo_perfil": mapa_grupo_perfil,
                "modelo": modelo,
                "api_base": api_base,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_oidc_saida_mapa_grupo_perfil import ProvedorOidcSaidaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        habilitado = d.pop("habilitado")

        rotulo = d.pop("rotulo")

        ordem = d.pop("ordem")

        issuer = d.pop("issuer")

        client_id = d.pop("client_id")

        tem_client_secret = d.pop("tem_client_secret")

        escopos = d.pop("escopos")

        atributo_grupos = d.pop("atributo_grupos")

        def _parse_perfil_padrao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao"))

        mapa_grupo_perfil = ProvedorOidcSaidaMapaGrupoPerfil.from_dict(d.pop("mapa_grupo_perfil"))

        modelo = d.pop("modelo")

        def _parse_api_base(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        api_base = _parse_api_base(d.pop("api_base"))

        provedor_oidc_saida = cls(
            id=id,
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            issuer=issuer,
            client_id=client_id,
            tem_client_secret=tem_client_secret,
            escopos=escopos,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
            modelo=modelo,
            api_base=api_base,
        )

        provedor_oidc_saida.additional_properties = d
        return provedor_oidc_saida

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
