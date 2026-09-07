from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.org_saida_armazenamento import OrgSaidaArmazenamento
    from ..models.org_saida_auth import OrgSaidaAuth
    from ..models.org_saida_mapa import OrgSaidaMapa
    from ..models.org_saida_usuarios import OrgSaidaUsuarios


T = TypeVar("T", bound="OrgSaida")


@_attrs_define
class OrgSaida:
    """
    Attributes:
        slug (str):
        nome (str):
        ativo (bool):
        cor (str):
        logo (None | str):
        idioma_padrao (str):
        mapa (OrgSaidaMapa):
        armazenamento (OrgSaidaArmazenamento):
        usuarios (OrgSaidaUsuarios):
        auth (OrgSaidaAuth):
    """

    slug: str
    nome: str
    ativo: bool
    cor: str
    logo: None | str
    idioma_padrao: str
    mapa: OrgSaidaMapa
    armazenamento: OrgSaidaArmazenamento
    usuarios: OrgSaidaUsuarios
    auth: OrgSaidaAuth
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        slug = self.slug

        nome = self.nome

        ativo = self.ativo

        cor = self.cor

        logo: None | str
        logo = self.logo

        idioma_padrao = self.idioma_padrao

        mapa = self.mapa.to_dict()

        armazenamento = self.armazenamento.to_dict()

        usuarios = self.usuarios.to_dict()

        auth = self.auth.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "slug": slug,
                "nome": nome,
                "ativo": ativo,
                "cor": cor,
                "logo": logo,
                "idioma_padrao": idioma_padrao,
                "mapa": mapa,
                "armazenamento": armazenamento,
                "usuarios": usuarios,
                "auth": auth,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.org_saida_armazenamento import OrgSaidaArmazenamento  # noqa: PLC0415
        from ..models.org_saida_auth import OrgSaidaAuth  # noqa: PLC0415
        from ..models.org_saida_mapa import OrgSaidaMapa  # noqa: PLC0415
        from ..models.org_saida_usuarios import OrgSaidaUsuarios  # noqa: PLC0415

        d = dict(src_dict)
        slug = d.pop("slug")

        nome = d.pop("nome")

        ativo = d.pop("ativo")

        cor = d.pop("cor")

        def _parse_logo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        logo = _parse_logo(d.pop("logo"))

        idioma_padrao = d.pop("idioma_padrao")

        mapa = OrgSaidaMapa.from_dict(d.pop("mapa"))

        armazenamento = OrgSaidaArmazenamento.from_dict(d.pop("armazenamento"))

        usuarios = OrgSaidaUsuarios.from_dict(d.pop("usuarios"))

        auth = OrgSaidaAuth.from_dict(d.pop("auth"))

        org_saida = cls(
            slug=slug,
            nome=nome,
            ativo=ativo,
            cor=cor,
            logo=logo,
            idioma_padrao=idioma_padrao,
            mapa=mapa,
            armazenamento=armazenamento,
            usuarios=usuarios,
            auth=auth,
        )

        org_saida.additional_properties = d
        return org_saida

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
