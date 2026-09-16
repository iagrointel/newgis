from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.provedor_saml_entrada_mapa_grupo_perfil import ProvedorSamlEntradaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorSamlEntrada")


@_attrs_define
class ProvedorSamlEntrada:
    """
    Attributes:
        habilitado (bool | Unset):  Default: True.
        rotulo (str | Unset):  Default: 'Entrar com a organização (SAML)'.
        ordem (int | Unset):  Default: 0.
        metadado_url (None | str | Unset):
        metadado_xml (None | str | Unset):
        idp_entity_id (None | str | Unset):
        idp_sso_url (None | str | Unset):
        idp_slo_url (None | str | Unset):
        idp_certificado (None | str | Unset):
        assercao_cifrada (bool | Unset):  Default: False.
        formato_nameid (str | Unset):  Default: 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'.
        atributo_login (None | str | Unset):
        atributo_email (str | Unset):  Default: 'email'.
        atributo_nome (str | Unset):  Default: 'name'.
        atributo_grupos (str | Unset):  Default: 'groups'.
        perfil_padrao (None | str | Unset):
        mapa_grupo_perfil (ProvedorSamlEntradaMapaGrupoPerfil | Unset):
    """

    habilitado: bool | Unset = True
    rotulo: str | Unset = "Entrar com a organização (SAML)"
    ordem: int | Unset = 0
    metadado_url: None | str | Unset = UNSET
    metadado_xml: None | str | Unset = UNSET
    idp_entity_id: None | str | Unset = UNSET
    idp_sso_url: None | str | Unset = UNSET
    idp_slo_url: None | str | Unset = UNSET
    idp_certificado: None | str | Unset = UNSET
    assercao_cifrada: bool | Unset = False
    formato_nameid: str | Unset = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    atributo_login: None | str | Unset = UNSET
    atributo_email: str | Unset = "email"
    atributo_nome: str | Unset = "name"
    atributo_grupos: str | Unset = "groups"
    perfil_padrao: None | str | Unset = UNSET
    mapa_grupo_perfil: ProvedorSamlEntradaMapaGrupoPerfil | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        habilitado = self.habilitado

        rotulo = self.rotulo

        ordem = self.ordem

        metadado_url: None | str | Unset
        if isinstance(self.metadado_url, Unset):
            metadado_url = UNSET
        else:
            metadado_url = self.metadado_url

        metadado_xml: None | str | Unset
        if isinstance(self.metadado_xml, Unset):
            metadado_xml = UNSET
        else:
            metadado_xml = self.metadado_xml

        idp_entity_id: None | str | Unset
        if isinstance(self.idp_entity_id, Unset):
            idp_entity_id = UNSET
        else:
            idp_entity_id = self.idp_entity_id

        idp_sso_url: None | str | Unset
        if isinstance(self.idp_sso_url, Unset):
            idp_sso_url = UNSET
        else:
            idp_sso_url = self.idp_sso_url

        idp_slo_url: None | str | Unset
        if isinstance(self.idp_slo_url, Unset):
            idp_slo_url = UNSET
        else:
            idp_slo_url = self.idp_slo_url

        idp_certificado: None | str | Unset
        if isinstance(self.idp_certificado, Unset):
            idp_certificado = UNSET
        else:
            idp_certificado = self.idp_certificado

        assercao_cifrada = self.assercao_cifrada

        formato_nameid = self.formato_nameid

        atributo_login: None | str | Unset
        if isinstance(self.atributo_login, Unset):
            atributo_login = UNSET
        else:
            atributo_login = self.atributo_login

        atributo_email = self.atributo_email

        atributo_nome = self.atributo_nome

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
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if metadado_url is not UNSET:
            field_dict["metadado_url"] = metadado_url
        if metadado_xml is not UNSET:
            field_dict["metadado_xml"] = metadado_xml
        if idp_entity_id is not UNSET:
            field_dict["idp_entity_id"] = idp_entity_id
        if idp_sso_url is not UNSET:
            field_dict["idp_sso_url"] = idp_sso_url
        if idp_slo_url is not UNSET:
            field_dict["idp_slo_url"] = idp_slo_url
        if idp_certificado is not UNSET:
            field_dict["idp_certificado"] = idp_certificado
        if assercao_cifrada is not UNSET:
            field_dict["assercao_cifrada"] = assercao_cifrada
        if formato_nameid is not UNSET:
            field_dict["formato_nameid"] = formato_nameid
        if atributo_login is not UNSET:
            field_dict["atributo_login"] = atributo_login
        if atributo_email is not UNSET:
            field_dict["atributo_email"] = atributo_email
        if atributo_nome is not UNSET:
            field_dict["atributo_nome"] = atributo_nome
        if atributo_grupos is not UNSET:
            field_dict["atributo_grupos"] = atributo_grupos
        if perfil_padrao is not UNSET:
            field_dict["perfil_padrao"] = perfil_padrao
        if mapa_grupo_perfil is not UNSET:
            field_dict["mapa_grupo_perfil"] = mapa_grupo_perfil

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_saml_entrada_mapa_grupo_perfil import ProvedorSamlEntradaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        habilitado = d.pop("habilitado", UNSET)

        rotulo = d.pop("rotulo", UNSET)

        ordem = d.pop("ordem", UNSET)

        def _parse_metadado_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        metadado_url = _parse_metadado_url(d.pop("metadado_url", UNSET))

        def _parse_metadado_xml(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        metadado_xml = _parse_metadado_xml(d.pop("metadado_xml", UNSET))

        def _parse_idp_entity_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idp_entity_id = _parse_idp_entity_id(d.pop("idp_entity_id", UNSET))

        def _parse_idp_sso_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idp_sso_url = _parse_idp_sso_url(d.pop("idp_sso_url", UNSET))

        def _parse_idp_slo_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idp_slo_url = _parse_idp_slo_url(d.pop("idp_slo_url", UNSET))

        def _parse_idp_certificado(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idp_certificado = _parse_idp_certificado(d.pop("idp_certificado", UNSET))

        assercao_cifrada = d.pop("assercao_cifrada", UNSET)

        formato_nameid = d.pop("formato_nameid", UNSET)

        def _parse_atributo_login(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        atributo_login = _parse_atributo_login(d.pop("atributo_login", UNSET))

        atributo_email = d.pop("atributo_email", UNSET)

        atributo_nome = d.pop("atributo_nome", UNSET)

        atributo_grupos = d.pop("atributo_grupos", UNSET)

        def _parse_perfil_padrao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao", UNSET))

        _mapa_grupo_perfil = d.pop("mapa_grupo_perfil", UNSET)
        mapa_grupo_perfil: ProvedorSamlEntradaMapaGrupoPerfil | Unset
        if isinstance(_mapa_grupo_perfil, Unset):
            mapa_grupo_perfil = UNSET
        else:
            mapa_grupo_perfil = ProvedorSamlEntradaMapaGrupoPerfil.from_dict(_mapa_grupo_perfil)

        provedor_saml_entrada = cls(
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            metadado_url=metadado_url,
            metadado_xml=metadado_xml,
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_slo_url=idp_slo_url,
            idp_certificado=idp_certificado,
            assercao_cifrada=assercao_cifrada,
            formato_nameid=formato_nameid,
            atributo_login=atributo_login,
            atributo_email=atributo_email,
            atributo_nome=atributo_nome,
            atributo_grupos=atributo_grupos,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        return provedor_saml_entrada
