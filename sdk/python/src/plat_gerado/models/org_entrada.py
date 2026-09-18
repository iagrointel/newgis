from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.bloco_galeria import BlocoGaleria
    from ..models.bloco_links import BlocoLinks
    from ..models.bloco_texto import BlocoTexto
    from ..models.org_entrada_auth import OrgEntradaAuth


T = TypeVar("T", bound="OrgEntrada")


@_attrs_define
class OrgEntrada:
    """
    Attributes:
        nome (str):
        contatos_admin (list[str]):
        cota_bytes (int):
        cota_usuarios (int):
        cor (str | Unset):  Default: '#2463a8'.
        resumo (None | str | Unset):
        contato (None | str | Unset):
        idioma_padrao (str | Unset):  Default: 'pt-BR'.
        unidades (str | Unset):  Default: 'metrico'.
        formato_data (str | Unset):  Default: 'dd/mm/aaaa'.
        formato_numero_data (str | Unset):  Default: 'idioma'.
        centro (list[float] | None | Unset):
        zoom (int | None | Unset):
        basemap (None | str | Unset):
        extent (list[float] | None | Unset):
        srid_padrao (int | None | Unset):
        pagina_inicial (list[BlocoGaleria | BlocoLinks | BlocoTexto] | Unset):
        galeria_destaque (None | str | Unset):
        banner_aviso (None | str | Unset):
        termo_acesso (None | str | Unset):
        auth (OrgEntradaAuth | Unset):
    """

    nome: str
    contatos_admin: list[str]
    cota_bytes: int
    cota_usuarios: int
    cor: str | Unset = "#2463a8"
    resumo: None | str | Unset = UNSET
    contato: None | str | Unset = UNSET
    idioma_padrao: str | Unset = "pt-BR"
    unidades: str | Unset = "metrico"
    formato_data: str | Unset = "dd/mm/aaaa"
    formato_numero_data: str | Unset = "idioma"
    centro: list[float] | None | Unset = UNSET
    zoom: int | None | Unset = UNSET
    basemap: None | str | Unset = UNSET
    extent: list[float] | None | Unset = UNSET
    srid_padrao: int | None | Unset = UNSET
    pagina_inicial: list[BlocoGaleria | BlocoLinks | BlocoTexto] | Unset = UNSET
    galeria_destaque: None | str | Unset = UNSET
    banner_aviso: None | str | Unset = UNSET
    termo_acesso: None | str | Unset = UNSET
    auth: OrgEntradaAuth | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.bloco_links import BlocoLinks  # noqa: PLC0415
        from ..models.bloco_texto import BlocoTexto  # noqa: PLC0415

        nome = self.nome

        contatos_admin = self.contatos_admin

        cota_bytes = self.cota_bytes

        cota_usuarios = self.cota_usuarios

        cor = self.cor

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        contato: None | str | Unset
        if isinstance(self.contato, Unset):
            contato = UNSET
        else:
            contato = self.contato

        idioma_padrao = self.idioma_padrao

        unidades = self.unidades

        formato_data = self.formato_data

        formato_numero_data = self.formato_numero_data

        centro: list[float] | None | Unset
        if isinstance(self.centro, Unset):
            centro = UNSET
        elif isinstance(self.centro, list):
            centro = self.centro

        else:
            centro = self.centro

        zoom: int | None | Unset
        if isinstance(self.zoom, Unset):
            zoom = UNSET
        else:
            zoom = self.zoom

        basemap: None | str | Unset
        if isinstance(self.basemap, Unset):
            basemap = UNSET
        else:
            basemap = self.basemap

        extent: list[float] | None | Unset
        if isinstance(self.extent, Unset):
            extent = UNSET
        elif isinstance(self.extent, list):
            extent = self.extent

        else:
            extent = self.extent

        srid_padrao: int | None | Unset
        if isinstance(self.srid_padrao, Unset):
            srid_padrao = UNSET
        else:
            srid_padrao = self.srid_padrao

        pagina_inicial: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.pagina_inicial, Unset):
            pagina_inicial = []
            for pagina_inicial_item_data in self.pagina_inicial:
                pagina_inicial_item: dict[str, Any]
                if isinstance(pagina_inicial_item_data, BlocoTexto):
                    pagina_inicial_item = pagina_inicial_item_data.to_dict()
                elif isinstance(pagina_inicial_item_data, BlocoLinks):
                    pagina_inicial_item = pagina_inicial_item_data.to_dict()
                else:
                    pagina_inicial_item = pagina_inicial_item_data.to_dict()

                pagina_inicial.append(pagina_inicial_item)

        galeria_destaque: None | str | Unset
        if isinstance(self.galeria_destaque, Unset):
            galeria_destaque = UNSET
        else:
            galeria_destaque = self.galeria_destaque

        banner_aviso: None | str | Unset
        if isinstance(self.banner_aviso, Unset):
            banner_aviso = UNSET
        else:
            banner_aviso = self.banner_aviso

        termo_acesso: None | str | Unset
        if isinstance(self.termo_acesso, Unset):
            termo_acesso = UNSET
        else:
            termo_acesso = self.termo_acesso

        auth: dict[str, Any] | Unset = UNSET
        if not isinstance(self.auth, Unset):
            auth = self.auth.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "contatos_admin": contatos_admin,
                "cota_bytes": cota_bytes,
                "cota_usuarios": cota_usuarios,
            }
        )
        if cor is not UNSET:
            field_dict["cor"] = cor
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if contato is not UNSET:
            field_dict["contato"] = contato
        if idioma_padrao is not UNSET:
            field_dict["idioma_padrao"] = idioma_padrao
        if unidades is not UNSET:
            field_dict["unidades"] = unidades
        if formato_data is not UNSET:
            field_dict["formato_data"] = formato_data
        if formato_numero_data is not UNSET:
            field_dict["formato_numero_data"] = formato_numero_data
        if centro is not UNSET:
            field_dict["centro"] = centro
        if zoom is not UNSET:
            field_dict["zoom"] = zoom
        if basemap is not UNSET:
            field_dict["basemap"] = basemap
        if extent is not UNSET:
            field_dict["extent"] = extent
        if srid_padrao is not UNSET:
            field_dict["srid_padrao"] = srid_padrao
        if pagina_inicial is not UNSET:
            field_dict["pagina_inicial"] = pagina_inicial
        if galeria_destaque is not UNSET:
            field_dict["galeria_destaque"] = galeria_destaque
        if banner_aviso is not UNSET:
            field_dict["banner_aviso"] = banner_aviso
        if termo_acesso is not UNSET:
            field_dict["termo_acesso"] = termo_acesso
        if auth is not UNSET:
            field_dict["auth"] = auth

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.bloco_galeria import BlocoGaleria  # noqa: PLC0415
        from ..models.bloco_links import BlocoLinks  # noqa: PLC0415
        from ..models.bloco_texto import BlocoTexto  # noqa: PLC0415
        from ..models.org_entrada_auth import OrgEntradaAuth  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        contatos_admin = cast(list[str], d.pop("contatos_admin"))

        cota_bytes = d.pop("cota_bytes")

        cota_usuarios = d.pop("cota_usuarios")

        cor = d.pop("cor", UNSET)

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        def _parse_contato(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        contato = _parse_contato(d.pop("contato", UNSET))

        idioma_padrao = d.pop("idioma_padrao", UNSET)

        unidades = d.pop("unidades", UNSET)

        formato_data = d.pop("formato_data", UNSET)

        formato_numero_data = d.pop("formato_numero_data", UNSET)

        def _parse_centro(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                centro_type_0 = cast(list[float], data)

                return centro_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        centro = _parse_centro(d.pop("centro", UNSET))

        def _parse_zoom(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        zoom = _parse_zoom(d.pop("zoom", UNSET))

        def _parse_basemap(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        basemap = _parse_basemap(d.pop("basemap", UNSET))

        def _parse_extent(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                extent_type_0 = cast(list[float], data)

                return extent_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        extent = _parse_extent(d.pop("extent", UNSET))

        def _parse_srid_padrao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid_padrao = _parse_srid_padrao(d.pop("srid_padrao", UNSET))

        _pagina_inicial = d.pop("pagina_inicial", UNSET)
        pagina_inicial: list[BlocoGaleria | BlocoLinks | BlocoTexto] | Unset = UNSET
        if _pagina_inicial is not UNSET:
            pagina_inicial = []
            for pagina_inicial_item_data in _pagina_inicial:

                def _parse_pagina_inicial_item(data: object) -> BlocoGaleria | BlocoLinks | BlocoTexto:
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        pagina_inicial_item_type_0 = BlocoTexto.from_dict(data)

                        return pagina_inicial_item_type_0
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        pagina_inicial_item_type_1 = BlocoLinks.from_dict(data)

                        return pagina_inicial_item_type_1
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    if not isinstance(data, dict):
                        raise TypeError()
                    pagina_inicial_item_type_2 = BlocoGaleria.from_dict(data)

                    return pagina_inicial_item_type_2

                pagina_inicial_item = _parse_pagina_inicial_item(pagina_inicial_item_data)

                pagina_inicial.append(pagina_inicial_item)

        def _parse_galeria_destaque(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        galeria_destaque = _parse_galeria_destaque(d.pop("galeria_destaque", UNSET))

        def _parse_banner_aviso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        banner_aviso = _parse_banner_aviso(d.pop("banner_aviso", UNSET))

        def _parse_termo_acesso(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        termo_acesso = _parse_termo_acesso(d.pop("termo_acesso", UNSET))

        _auth = d.pop("auth", UNSET)
        auth: OrgEntradaAuth | Unset
        if isinstance(_auth, Unset):
            auth = UNSET
        else:
            auth = OrgEntradaAuth.from_dict(_auth)

        org_entrada = cls(
            nome=nome,
            contatos_admin=contatos_admin,
            cota_bytes=cota_bytes,
            cota_usuarios=cota_usuarios,
            cor=cor,
            resumo=resumo,
            contato=contato,
            idioma_padrao=idioma_padrao,
            unidades=unidades,
            formato_data=formato_data,
            formato_numero_data=formato_numero_data,
            centro=centro,
            zoom=zoom,
            basemap=basemap,
            extent=extent,
            srid_padrao=srid_padrao,
            pagina_inicial=pagina_inicial,
            galeria_destaque=galeria_destaque,
            banner_aviso=banner_aviso,
            termo_acesso=termo_acesso,
            auth=auth,
        )

        return org_entrada
