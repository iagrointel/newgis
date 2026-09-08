from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConviteEntrada")


@_attrs_define
class ConviteEntrada:
    """
    Attributes:
        usuario_id (int):
        papel (str | Unset):  Default: 'membro'.
    """

    usuario_id: int
    papel: str | Unset = "membro"

    def to_dict(self) -> dict[str, Any]:
        usuario_id = self.usuario_id

        papel = self.papel

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "usuario_id": usuario_id,
            }
        )
        if papel is not UNSET:
            field_dict["papel"] = papel

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        usuario_id = d.pop("usuario_id")

        papel = d.pop("papel", UNSET)

        convite_entrada = cls(
            usuario_id=usuario_id,
            papel=papel,
        )

        return convite_entrada
