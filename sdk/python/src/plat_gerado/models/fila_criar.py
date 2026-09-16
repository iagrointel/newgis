from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="FilaCriar")


@_attrs_define
class FilaCriar:
    """
    Attributes:
        titulo (str):
        camada_id (str):
        globalids (list[str] | Unset):
    """

    titulo: str
    camada_id: str
    globalids: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        titulo = self.titulo

        camada_id = self.camada_id

        globalids: list[str] | Unset = UNSET
        if not isinstance(self.globalids, Unset):
            globalids = self.globalids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "titulo": titulo,
                "camada_id": camada_id,
            }
        )
        if globalids is not UNSET:
            field_dict["globalids"] = globalids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        titulo = d.pop("titulo")

        camada_id = d.pop("camada_id")

        globalids = cast(list[str], d.pop("globalids", UNSET))

        fila_criar = cls(
            titulo=titulo,
            camada_id=camada_id,
            globalids=globalids,
        )

        return fila_criar
