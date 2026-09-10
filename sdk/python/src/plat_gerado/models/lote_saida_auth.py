from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.lote_saida_auth_recusados_item import LoteSaidaAuthRecusadosItem


T = TypeVar("T", bound="LoteSaidaAuth")


@_attrs_define
class LoteSaidaAuth:
    """
    Attributes:
        alterados (int):
        recusados (list[LoteSaidaAuthRecusadosItem]):
    """

    alterados: int
    recusados: list[LoteSaidaAuthRecusadosItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        alterados = self.alterados

        recusados = []
        for recusados_item_data in self.recusados:
            recusados_item = recusados_item_data.to_dict()
            recusados.append(recusados_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "alterados": alterados,
                "recusados": recusados,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lote_saida_auth_recusados_item import LoteSaidaAuthRecusadosItem  # noqa: PLC0415

        d = dict(src_dict)
        alterados = d.pop("alterados")

        recusados = []
        _recusados = d.pop("recusados")
        for recusados_item_data in _recusados:
            recusados_item = LoteSaidaAuthRecusadosItem.from_dict(recusados_item_data)

            recusados.append(recusados_item)

        lote_saida_auth = cls(
            alterados=alterados,
            recusados=recusados,
        )

        lote_saida_auth.additional_properties = d
        return lote_saida_auth

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
