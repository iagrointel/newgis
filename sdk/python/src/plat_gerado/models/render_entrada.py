from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.render_entrada_formato import RenderEntradaFormato
from ..types import UNSET, Unset

T = TypeVar("T", bound="RenderEntrada")


@_attrs_define
class RenderEntrada:
    """
    Attributes:
        mapa_id (None | str | Unset):
        largura (int | Unset):  Default: 1024.
        altura (int | Unset):  Default: 768.
        dpi (int | Unset):  Default: 96.
        formato (RenderEntradaFormato | Unset):  Default: RenderEntradaFormato.PNG.
        extensao (list[float] | None | Unset):
        zoom (float | None | Unset):
        centro (list[float] | None | Unset):
    """

    mapa_id: None | str | Unset = UNSET
    largura: int | Unset = 1024
    altura: int | Unset = 768
    dpi: int | Unset = 96
    formato: RenderEntradaFormato | Unset = RenderEntradaFormato.PNG
    extensao: list[float] | None | Unset = UNSET
    zoom: float | None | Unset = UNSET
    centro: list[float] | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        mapa_id: None | str | Unset
        if isinstance(self.mapa_id, Unset):
            mapa_id = UNSET
        else:
            mapa_id = self.mapa_id

        largura = self.largura

        altura = self.altura

        dpi = self.dpi

        formato: str | Unset = UNSET
        if not isinstance(self.formato, Unset):
            formato = self.formato.value

        extensao: list[float] | None | Unset
        if isinstance(self.extensao, Unset):
            extensao = UNSET
        elif isinstance(self.extensao, list):
            extensao = self.extensao

        else:
            extensao = self.extensao

        zoom: float | None | Unset
        if isinstance(self.zoom, Unset):
            zoom = UNSET
        else:
            zoom = self.zoom

        centro: list[float] | None | Unset
        if isinstance(self.centro, Unset):
            centro = UNSET
        elif isinstance(self.centro, list):
            centro = self.centro

        else:
            centro = self.centro

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if mapa_id is not UNSET:
            field_dict["mapa_id"] = mapa_id
        if largura is not UNSET:
            field_dict["largura"] = largura
        if altura is not UNSET:
            field_dict["altura"] = altura
        if dpi is not UNSET:
            field_dict["dpi"] = dpi
        if formato is not UNSET:
            field_dict["formato"] = formato
        if extensao is not UNSET:
            field_dict["extensao"] = extensao
        if zoom is not UNSET:
            field_dict["zoom"] = zoom
        if centro is not UNSET:
            field_dict["centro"] = centro

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_mapa_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mapa_id = _parse_mapa_id(d.pop("mapa_id", UNSET))

        largura = d.pop("largura", UNSET)

        altura = d.pop("altura", UNSET)

        dpi = d.pop("dpi", UNSET)

        _formato = d.pop("formato", UNSET)
        formato: RenderEntradaFormato | Unset
        if isinstance(_formato, Unset):
            formato = UNSET
        else:
            formato = RenderEntradaFormato(_formato)

        def _parse_extensao(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                extensao_type_0 = cast(list[float], data)

                return extensao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        extensao = _parse_extensao(d.pop("extensao", UNSET))

        def _parse_zoom(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        zoom = _parse_zoom(d.pop("zoom", UNSET))

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

        render_entrada = cls(
            mapa_id=mapa_id,
            largura=largura,
            altura=altura,
            dpi=dpi,
            formato=formato,
            extensao=extensao,
            zoom=zoom,
            centro=centro,
        )

        return render_entrada
