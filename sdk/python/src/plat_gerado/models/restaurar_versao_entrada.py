from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RestaurarVersaoEntrada")


@_attrs_define
class RestaurarVersaoEntrada:
    """
    Attributes:
        comentario (None | str | Unset):
    """

    comentario: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        comentario: None | str | Unset
        if isinstance(self.comentario, Unset):
            comentario = UNSET
        else:
            comentario = self.comentario

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if comentario is not UNSET:
            field_dict["comentario"] = comentario

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_comentario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        comentario = _parse_comentario(d.pop("comentario", UNSET))

        restaurar_versao_entrada = cls(
            comentario=comentario,
        )

        return restaurar_versao_entrada
