from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.colecao_saida import ColecaoSaida


T = TypeVar("T", bound="ColecoesPagina")


@_attrs_define
class ColecoesPagina:
    """
    Attributes:
        total (int):
        itens (list[ColecaoSaida]):
        do_cache (bool | Unset):  Default: False.
    """

    total: int
    itens: list[ColecaoSaida]
    do_cache: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        do_cache = self.do_cache

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "itens": itens,
            }
        )
        if do_cache is not UNSET:
            field_dict["do_cache"] = do_cache

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.colecao_saida import ColecaoSaida  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = ColecaoSaida.from_dict(itens_item_data)

            itens.append(itens_item)

        do_cache = d.pop("do_cache", UNSET)

        colecoes_pagina = cls(
            total=total,
            itens=itens,
            do_cache=do_cache,
        )

        colecoes_pagina.additional_properties = d
        return colecoes_pagina

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
