from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.provedor_sso_saida_mapa_grupo_perfil import ProvedorSsoSaidaMapaGrupoPerfil


T = TypeVar("T", bound="ProvedorSsoSaida")


@_attrs_define
class ProvedorSsoSaida:
    """
    Attributes:
        tipo (str):
        habilitado (bool):
        emissor (None | str):
        cliente_id (None | str):
        tem_segredo (bool):
        idp_entidade (None | str):
        idp_url_sso (None | str):
        idp_certificado (None | str):
        claim_grupos (None | str):
        claim_login (None | str):
        perfil_padrao (None | str):
        mapa_grupo_perfil (ProvedorSsoSaidaMapaGrupoPerfil):
    """

    tipo: str
    habilitado: bool
    emissor: None | str
    cliente_id: None | str
    tem_segredo: bool
    idp_entidade: None | str
    idp_url_sso: None | str
    idp_certificado: None | str
    claim_grupos: None | str
    claim_login: None | str
    perfil_padrao: None | str
    mapa_grupo_perfil: ProvedorSsoSaidaMapaGrupoPerfil
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        habilitado = self.habilitado

        emissor: None | str
        emissor = self.emissor

        cliente_id: None | str
        cliente_id = self.cliente_id

        tem_segredo = self.tem_segredo

        idp_entidade: None | str
        idp_entidade = self.idp_entidade

        idp_url_sso: None | str
        idp_url_sso = self.idp_url_sso

        idp_certificado: None | str
        idp_certificado = self.idp_certificado

        claim_grupos: None | str
        claim_grupos = self.claim_grupos

        claim_login: None | str
        claim_login = self.claim_login

        perfil_padrao: None | str
        perfil_padrao = self.perfil_padrao

        mapa_grupo_perfil = self.mapa_grupo_perfil.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo": tipo,
                "habilitado": habilitado,
                "emissor": emissor,
                "cliente_id": cliente_id,
                "tem_segredo": tem_segredo,
                "idp_entidade": idp_entidade,
                "idp_url_sso": idp_url_sso,
                "idp_certificado": idp_certificado,
                "claim_grupos": claim_grupos,
                "claim_login": claim_login,
                "perfil_padrao": perfil_padrao,
                "mapa_grupo_perfil": mapa_grupo_perfil,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedor_sso_saida_mapa_grupo_perfil import ProvedorSsoSaidaMapaGrupoPerfil  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

        habilitado = d.pop("habilitado")

        def _parse_emissor(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        emissor = _parse_emissor(d.pop("emissor"))

        def _parse_cliente_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        cliente_id = _parse_cliente_id(d.pop("cliente_id"))

        tem_segredo = d.pop("tem_segredo")

        def _parse_idp_entidade(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idp_entidade = _parse_idp_entidade(d.pop("idp_entidade"))

        def _parse_idp_url_sso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idp_url_sso = _parse_idp_url_sso(d.pop("idp_url_sso"))

        def _parse_idp_certificado(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idp_certificado = _parse_idp_certificado(d.pop("idp_certificado"))

        def _parse_claim_grupos(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        claim_grupos = _parse_claim_grupos(d.pop("claim_grupos"))

        def _parse_claim_login(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        claim_login = _parse_claim_login(d.pop("claim_login"))

        def _parse_perfil_padrao(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        perfil_padrao = _parse_perfil_padrao(d.pop("perfil_padrao"))

        mapa_grupo_perfil = ProvedorSsoSaidaMapaGrupoPerfil.from_dict(d.pop("mapa_grupo_perfil"))

        provedor_sso_saida = cls(
            tipo=tipo,
            habilitado=habilitado,
            emissor=emissor,
            cliente_id=cliente_id,
            tem_segredo=tem_segredo,
            idp_entidade=idp_entidade,
            idp_url_sso=idp_url_sso,
            idp_certificado=idp_certificado,
            claim_grupos=claim_grupos,
            claim_login=claim_login,
            perfil_padrao=perfil_padrao,
            mapa_grupo_perfil=mapa_grupo_perfil,
        )

        provedor_sso_saida.additional_properties = d
        return provedor_sso_saida

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
