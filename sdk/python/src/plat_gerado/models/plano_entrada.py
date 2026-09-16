from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mudanca_entrada import MudancaEntrada


T = TypeVar("T", bound="PlanoEntrada")


@_attrs_define
class PlanoEntrada:
    """
    Attributes:
        mudancas (list[MudancaEntrada] | Unset):
    """

    mudancas: list[MudancaEntrada] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        mudancas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.mudancas, Unset):
            mudancas = []
            for mudancas_item_data in self.mudancas:
                mudancas_item = mudancas_item_data.to_dict()
                mudancas.append(mudancas_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if mudancas is not UNSET:
            field_dict["mudancas"] = mudancas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mudanca_entrada import MudancaEntrada  # noqa: PLC0415

        d = dict(src_dict)
        _mudancas = d.pop("mudancas", UNSET)
        mudancas: list[MudancaEntrada] | Unset = UNSET
        if _mudancas is not UNSET:
            mudancas = []
            for mudancas_item_data in _mudancas:
                mudancas_item = MudancaEntrada.from_dict(mudancas_item_data)

                mudancas.append(mudancas_item)

        plano_entrada = cls(
            mudancas=mudancas,
        )

        return plano_entrada
