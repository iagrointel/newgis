from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.lista_notificacoes_itens_item import ListaNotificacoesItensItem


T = TypeVar("T", bound="ListaNotificacoes")


@_attrs_define
class ListaNotificacoes:
    """
    Attributes:
        total (int):
        nao_lidas (int):
        itens (list[ListaNotificacoesItensItem]):
    """

    total: int
    nao_lidas: int
    itens: list[ListaNotificacoesItensItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        nao_lidas = self.nao_lidas

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "nao_lidas": nao_lidas,
                "itens": itens,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lista_notificacoes_itens_item import ListaNotificacoesItensItem  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        nao_lidas = d.pop("nao_lidas")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = ListaNotificacoesItensItem.from_dict(itens_item_data)

            itens.append(itens_item)

        lista_notificacoes = cls(
            total=total,
            nao_lidas=nao_lidas,
            itens=itens,
        )

        lista_notificacoes.additional_properties = d
        return lista_notificacoes

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
