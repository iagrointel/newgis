from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BuscaEntrada")


@_attrs_define
class BuscaEntrada:
    """
    Attributes:
        url (str): endereço do CSW 2.0.2
        texto (None | str | Unset):
        bbox (list[float] | None | Unset): [oeste, sul, leste, norte] em graus
        inicio (int | Unset):  Default: 1.
        maximo (int | Unset):  Default: 10.
    """

    url: str
    texto: None | str | Unset = UNSET
    bbox: list[float] | None | Unset = UNSET
    inicio: int | Unset = 1
    maximo: int | Unset = 10

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        texto: None | str | Unset
        if isinstance(self.texto, Unset):
            texto = UNSET
        else:
            texto = self.texto

        bbox: list[float] | None | Unset
        if isinstance(self.bbox, Unset):
            bbox = UNSET
        elif isinstance(self.bbox, list):
            bbox = self.bbox

        else:
            bbox = self.bbox

        inicio = self.inicio

        maximo = self.maximo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "url": url,
            }
        )
        if texto is not UNSET:
            field_dict["texto"] = texto
        if bbox is not UNSET:
            field_dict["bbox"] = bbox
        if inicio is not UNSET:
            field_dict["inicio"] = inicio
        if maximo is not UNSET:
            field_dict["maximo"] = maximo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        url = d.pop("url")

        def _parse_texto(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        texto = _parse_texto(d.pop("texto", UNSET))

        def _parse_bbox(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                bbox_type_0 = cast(list[float], data)

                return bbox_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        bbox = _parse_bbox(d.pop("bbox", UNSET))

        inicio = d.pop("inicio", UNSET)

        maximo = d.pop("maximo", UNSET)

        busca_entrada = cls(
            url=url,
            texto=texto,
            bbox=bbox,
            inicio=inicio,
            maximo=maximo,
        )

        return busca_entrada
