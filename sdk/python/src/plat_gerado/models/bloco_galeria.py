from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="BlocoGaleria")


@_attrs_define
class BlocoGaleria:
    """Galeria de itens: mostra os itens do grupo `galeria_destaque` (a fonte é única por inquilino, como o
    'featured content' da aba Gallery da Esri — o bloco só decide ONDE ela aparece na página inicial).

        Attributes:
            tipo (Literal['galeria']):
            titulo (str | Unset):  Default: ''.
    """

    tipo: Literal["galeria"]
    titulo: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = cast(Literal["galeria"], d.pop("tipo"))
        if tipo != "galeria":
            raise ValueError(f"tipo must match const 'galeria', got '{tipo}'")

        titulo = d.pop("titulo", UNSET)

        bloco_galeria = cls(
            tipo=tipo,
            titulo=titulo,
        )

        return bloco_galeria
