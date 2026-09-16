from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.importacao_pacote_itens_item import ImportacaoPacoteItensItem


T = TypeVar("T", bound="ImportacaoPacote")


@_attrs_define
class ImportacaoPacote:
    """
    Attributes:
        raiz (str):
        itens (list[ImportacaoPacoteItensItem]):
        fontes_mapeadas (int):
    """

    raiz: str
    itens: list[ImportacaoPacoteItensItem]
    fontes_mapeadas: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raiz = self.raiz

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        fontes_mapeadas = self.fontes_mapeadas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "raiz": raiz,
                "itens": itens,
                "fontes_mapeadas": fontes_mapeadas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.importacao_pacote_itens_item import ImportacaoPacoteItensItem  # noqa: PLC0415

        d = dict(src_dict)
        raiz = d.pop("raiz")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = ImportacaoPacoteItensItem.from_dict(itens_item_data)

            itens.append(itens_item)

        fontes_mapeadas = d.pop("fontes_mapeadas")

        importacao_pacote = cls(
            raiz=raiz,
            itens=itens,
            fontes_mapeadas=fontes_mapeadas,
        )

        importacao_pacote.additional_properties = d
        return importacao_pacote

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
