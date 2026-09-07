from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.org_entrada_auth import OrgEntradaAuth


T = TypeVar("T", bound="OrgEntrada")


@_attrs_define
class OrgEntrada:
    """
    Attributes:
        nome (str):
        cota_bytes (int):
        cota_usuarios (int):
        cor (str | Unset):  Default: '#2463a8'.
        idioma_padrao (str | Unset):  Default: 'pt-BR'.
        centro (list[float] | None | Unset):
        zoom (int | None | Unset):
        basemap (None | str | Unset):
        srid_padrao (int | None | Unset):
        auth (OrgEntradaAuth | Unset):
    """

    nome: str
    cota_bytes: int
    cota_usuarios: int
    cor: str | Unset = "#2463a8"
    idioma_padrao: str | Unset = "pt-BR"
    centro: list[float] | None | Unset = UNSET
    zoom: int | None | Unset = UNSET
    basemap: None | str | Unset = UNSET
    srid_padrao: int | None | Unset = UNSET
    auth: OrgEntradaAuth | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        cota_bytes = self.cota_bytes

        cota_usuarios = self.cota_usuarios

        cor = self.cor

        idioma_padrao = self.idioma_padrao

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

        srid_padrao: int | None | Unset
        if isinstance(self.srid_padrao, Unset):
            srid_padrao = UNSET
        else:
            srid_padrao = self.srid_padrao

        auth: dict[str, Any] | Unset = UNSET
        if not isinstance(self.auth, Unset):
            auth = self.auth.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "cota_bytes": cota_bytes,
                "cota_usuarios": cota_usuarios,
            }
        )
        if cor is not UNSET:
            field_dict["cor"] = cor
        if idioma_padrao is not UNSET:
            field_dict["idioma_padrao"] = idioma_padrao
        if centro is not UNSET:
            field_dict["centro"] = centro
        if zoom is not UNSET:
            field_dict["zoom"] = zoom
        if basemap is not UNSET:
            field_dict["basemap"] = basemap
        if srid_padrao is not UNSET:
            field_dict["srid_padrao"] = srid_padrao
        if auth is not UNSET:
            field_dict["auth"] = auth

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.org_entrada_auth import OrgEntradaAuth  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        cota_bytes = d.pop("cota_bytes")

        cota_usuarios = d.pop("cota_usuarios")

        cor = d.pop("cor", UNSET)

        idioma_padrao = d.pop("idioma_padrao", UNSET)

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

        def _parse_srid_padrao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        srid_padrao = _parse_srid_padrao(d.pop("srid_padrao", UNSET))

        _auth = d.pop("auth", UNSET)
        auth: OrgEntradaAuth | Unset
        if isinstance(_auth, Unset):
            auth = UNSET
        else:
            auth = OrgEntradaAuth.from_dict(_auth)

        org_entrada = cls(
            nome=nome,
            cota_bytes=cota_bytes,
            cota_usuarios=cota_usuarios,
            cor=cor,
            idioma_padrao=idioma_padrao,
            centro=centro,
            zoom=zoom,
            basemap=basemap,
            srid_padrao=srid_padrao,
            auth=auth,
        )

        return org_entrada
