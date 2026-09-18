from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.org_saida_armazenamento import OrgSaidaArmazenamento
    from ..models.org_saida_auth import OrgSaidaAuth
    from ..models.org_saida_mapa import OrgSaidaMapa
    from ..models.org_saida_pagina_inicial_item import OrgSaidaPaginaInicialItem
    from ..models.org_saida_regional import OrgSaidaRegional
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
        resumo (None | str):
        contato (None | str):
        contatos_admin (list[str]):
        idioma_padrao (str):
        regional (OrgSaidaRegional):
        mapa (OrgSaidaMapa):
        pagina_inicial (list[OrgSaidaPaginaInicialItem]):
        galeria_destaque (None | str):
        banner_aviso (None | str):
        termo_acesso (None | str):
        armazenamento (OrgSaidaArmazenamento):
        usuarios (OrgSaidaUsuarios):
        auth (OrgSaidaAuth):
    """

    slug: str
    nome: str
    ativo: bool
    cor: str
    logo: None | str
    resumo: None | str
    contato: None | str
    contatos_admin: list[str]
    idioma_padrao: str
    regional: OrgSaidaRegional
    mapa: OrgSaidaMapa
    pagina_inicial: list[OrgSaidaPaginaInicialItem]
    galeria_destaque: None | str
    banner_aviso: None | str
    termo_acesso: None | str
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

        resumo: None | str
        resumo = self.resumo

        contato: None | str
        contato = self.contato

        contatos_admin = self.contatos_admin

        idioma_padrao = self.idioma_padrao

        regional = self.regional.to_dict()

        mapa = self.mapa.to_dict()

        pagina_inicial = []
        for pagina_inicial_item_data in self.pagina_inicial:
            pagina_inicial_item = pagina_inicial_item_data.to_dict()
            pagina_inicial.append(pagina_inicial_item)

        galeria_destaque: None | str
        galeria_destaque = self.galeria_destaque

        banner_aviso: None | str
        banner_aviso = self.banner_aviso

        termo_acesso: None | str
        termo_acesso = self.termo_acesso

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
                "resumo": resumo,
                "contato": contato,
                "contatos_admin": contatos_admin,
                "idioma_padrao": idioma_padrao,
                "regional": regional,
                "mapa": mapa,
                "pagina_inicial": pagina_inicial,
                "galeria_destaque": galeria_destaque,
                "banner_aviso": banner_aviso,
                "termo_acesso": termo_acesso,
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
        from ..models.org_saida_pagina_inicial_item import OrgSaidaPaginaInicialItem  # noqa: PLC0415
        from ..models.org_saida_regional import OrgSaidaRegional  # noqa: PLC0415
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

        def _parse_resumo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resumo = _parse_resumo(d.pop("resumo"))

        def _parse_contato(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        contato = _parse_contato(d.pop("contato"))

        contatos_admin = cast(list[str], d.pop("contatos_admin"))

        idioma_padrao = d.pop("idioma_padrao")

        regional = OrgSaidaRegional.from_dict(d.pop("regional"))

        mapa = OrgSaidaMapa.from_dict(d.pop("mapa"))

        pagina_inicial = []
        _pagina_inicial = d.pop("pagina_inicial")
        for pagina_inicial_item_data in _pagina_inicial:
            pagina_inicial_item = OrgSaidaPaginaInicialItem.from_dict(pagina_inicial_item_data)

            pagina_inicial.append(pagina_inicial_item)

        def _parse_galeria_destaque(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        galeria_destaque = _parse_galeria_destaque(d.pop("galeria_destaque"))

        def _parse_banner_aviso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        banner_aviso = _parse_banner_aviso(d.pop("banner_aviso"))

        def _parse_termo_acesso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        termo_acesso = _parse_termo_acesso(d.pop("termo_acesso"))

        armazenamento = OrgSaidaArmazenamento.from_dict(d.pop("armazenamento"))

        usuarios = OrgSaidaUsuarios.from_dict(d.pop("usuarios"))

        auth = OrgSaidaAuth.from_dict(d.pop("auth"))

        org_saida = cls(
            slug=slug,
            nome=nome,
            ativo=ativo,
            cor=cor,
            logo=logo,
            resumo=resumo,
            contato=contato,
            contatos_admin=contatos_admin,
            idioma_padrao=idioma_padrao,
            regional=regional,
            mapa=mapa,
            pagina_inicial=pagina_inicial,
            galeria_destaque=galeria_destaque,
            banner_aviso=banner_aviso,
            termo_acesso=termo_acesso,
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
