from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PublicarEntradaVersionamento")


@_attrs_define
class PublicarEntradaVersionamento:
    """
    Attributes:
        modo (str | Unset):  Default: 'fechar'.
    """

    modo: str | Unset = "fechar"

    def to_dict(self) -> dict[str, Any]:
        modo = self.modo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if modo is not UNSET:
            field_dict["modo"] = modo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        modo = d.pop("modo", UNSET)

        publicar_entrada_versionamento = cls(
            modo=modo,
        )

        return publicar_entrada_versionamento
