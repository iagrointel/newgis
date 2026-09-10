from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PublicarCamadaEntrada")


@_attrs_define
class PublicarCamadaEntrada:
    """
    Attributes:
        titulo (None | str | Unset):
    """

    titulo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        publicar_camada_entrada = cls(
            titulo=titulo,
        )

        return publicar_camada_entrada
