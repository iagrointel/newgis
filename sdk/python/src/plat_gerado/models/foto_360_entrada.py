from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="Foto360Entrada")


@_attrs_define
class Foto360Entrada:
    """
    Attributes:
        arquivo_id (str):
        titulo (None | str | Unset):
    """

    arquivo_id: str
    titulo: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        arquivo_id = self.arquivo_id

        titulo: None | str | Unset
        if isinstance(self.titulo, Unset):
            titulo = UNSET
        else:
            titulo = self.titulo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "arquivo_id": arquivo_id,
            }
        )
        if titulo is not UNSET:
            field_dict["titulo"] = titulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        arquivo_id = d.pop("arquivo_id")

        def _parse_titulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        titulo = _parse_titulo(d.pop("titulo", UNSET))

        foto_360_entrada = cls(
            arquivo_id=arquivo_id,
            titulo=titulo,
        )

        return foto_360_entrada
