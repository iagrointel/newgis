from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PublicarEntrada")


@_attrs_define
class PublicarEntrada:
    """
    Attributes:
        item_id (str):
        titulo (None | str | Unset):
    """

    item_id: str
    titulo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "item_id": item_id,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        item_id = d.pop("item_id")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        publicar_entrada = cls(
            item_id=item_id,
            titulo=titulo,
        )

        return publicar_entrada
