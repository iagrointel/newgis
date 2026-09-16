from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.provedor_saml_saida_mapa_grupo_perfil import ProvedorSamlSaidaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorSamlSaida")


@_attrs_define
class ProvedorSamlSaida:
    """
    Attributes:
        id (int):
        habilitado (bool):
        rotulo (str):
        ordem (int):
        idp_entity_id (str):
        idp_sso_url (str):
        idp_slo_url (None | str):
        idp_certificados (list[str]):
        idp_metadado_url (None | str):
        sp_certificado (str):
        sp_metadata_url (str):
        assercao_cifrada (bool):
        formato_nameid (str):
        atributo_login (None | str):
        atributo_email (str):
        atributo_nome (str):
        atributo_grupos (str):
        perfil_padrao (None | str):
        mapa_grupo_perfil (ProvedorSamlSaidaMapaGrupoPerfil):
    """

    id: int
    habilitado: bool
    rotulo: str
    ordem: int
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: None | str
    idp_certificados: list[str]
    idp_metadado_url: None | str
    sp_certificado: str
    sp_metadata_url: str
    assercao_cifrada: bool
    formato_nameid: str
    atributo_login: None | str
    atributo_email: str
    atributo_nome: str
    atributo_grupos: str
    perfil_padrao: None | str
    mapa_grupo_perfil: ProvedorSamlSaidaMapaGrupoPerfil
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        habilitado = self.habilitado

        rotulo = self.rotulo

        ordem = self.ordem

        idp_entity_id = self.idp_entity_id

        idp_sso_url = self.idp_sso_url

        idp_slo_url: None | str
        idp_slo_url = self.idp_slo_url

        idp_certificados = self.idp_certificados

        idp_metadado_url: None | str
        idp_metadado_url = self.idp_metadado_url

        sp_certificado = self.sp_certificado

        sp_metadata_url = self.sp_metadata_url

        assercao_cifrada = self.assercao_cifrada

        formato_nameid = self.formato_nameid

        atributo_login: None | str
        atributo_login = self.atributo_login

        atributo_email = self.atributo_email

        atributo_nome = self.atributo_nome

        atributo_grupos = self.atributo_grupos

        perfil_padrao: None | str
        perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "habilitado": habilitado,
                "rotulo": rotulo,
                "ordem": ordem,
                "idp_entity_id": idp_entity_id,
                "idp_sso_url": idp_sso_url,
                "idp_slo_url": idp_slo_url,
                "idp_certificados": idp_certificados,
                "idp_metadado_url": idp_metadado_url,
                "sp_certificado": sp_certificado,
                "sp_metadata_url": sp_metadata_url,
                "assercao_cifrada": assercao_cifrada,
                "formato_nameid": formato_nameid,
                "atributo_login": atributo_login,
                "atributo_email": atributo_email,
                "atributo_nome": atributo_nome,
                "atributo_grupos": atributo_grupos,
                "perfil_padrao": perfil_padrao,
                "mapa_grupo_perfil": mapa_grupo_perfil,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_saml_saida_mapa_grupo_perfil import ProvedorSamlSaidaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        id = d.pop("id")

        habilitado = d.pop("habilitado")

        rotulo = d.pop("rotulo")

        ordem = d.pop("ordem")

        idp_entity_id = d.pop("idp_entity_id")

        idp_sso_url = d.pop("idp_sso_url")

        def _parse_idp_slo_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idp_slo_url = _parse_idp_slo_url(d.pop("idp_slo_url"))

        idp_certificados = cast(list[str], d.pop("idp_certificados"))

        def _parse_idp_metadado_url(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idp_metadado_url = _parse_idp_metadado_url(d.pop("idp_metadado_url"))

        sp_certificado = d.pop("sp_certificado")

        sp_metadata_url = d.pop("sp_metadata_url")

        assercao_cifrada = d.pop("assercao_cifrada")

        formato_nameid = d.pop("formato_nameid")

        def _parse_atributo_login(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        atributo_login = _parse_atributo_login(d.pop("atributo_login"))

        atributo_email = d.pop("atributo_email")

        atributo_nome = d.pop("atributo_nome")

        atributo_grupos = d.pop("atributo_grupos")

        def _parse_perfil_padrao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao"))

        mapa_grupo_perfil = ProvedorSamlSaidaMapaGrupoPerfil.from_dict(d.pop("mapa_grupo_perfil"))

        provedor_saml_saida = cls(
            id=id,
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_slo_url=idp_slo_url,
            idp_certificados=idp_certificados,
            idp_metadado_url=idp_metadado_url,
            sp_certificado=sp_certificado,
            sp_metadata_url=sp_metadata_url,
            assercao_cifrada=assercao_cifrada,
            formato_nameid=formato_nameid,
            atributo_login=atributo_login,
            atributo_email=atributo_email,
            atributo_nome=atributo_nome,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        provedor_saml_saida.additional_properties = d
        return provedor_saml_saida

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
