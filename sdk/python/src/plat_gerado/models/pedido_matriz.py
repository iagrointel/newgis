from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoMatriz")


@_attrs_define
class PedidoMatriz:
    """
    Attributes:
        origens (list[list[float]]):
        destinos (list[list[float]]):
        perfil (Literal['carro'] | Unset):  Default: 'carro'.
    """

    origens: list[list[float]]
    destinos: list[list[float]]
    perfil: Literal["carro"] | Unset = "carro"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        origens = []
        for origens_item_data in self.origens:
            origens_item = origens_item_data

            origens.append(origens_item)

        destinos = []
        for destinos_item_data in self.destinos:
            destinos_item = destinos_item_data

            destinos.append(destinos_item)

        perfil = self.perfil

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "origens": origens,
                "destinos": destinos,
            }
        )
        if perfil is not UNSET:
            field_dict["perfil"] = perfil

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        origens = []
        _origens = d.pop("origens")
        for origens_item_data in _origens:
            origens_item = cast(list[float], origens_item_data)

            origens.append(origens_item)

        destinos = []
        _destinos = d.pop("destinos")
        for destinos_item_data in _destinos:
            destinos_item = cast(list[float], destinos_item_data)

            destinos.append(destinos_item)

        perfil = cast(Literal["carro"] | Unset, d.pop("perfil", UNSET))
        if perfil != "carro" and not isinstance(perfil, Unset):
            raise ValueError(f"perfil must match const 'carro', got '{perfil}'")

        pedido_matriz = cls(
            origens=origens,
            destinos=destinos,
            perfil=perfil,
        )

        pedido_matriz.additional_properties = d
        return pedido_matriz

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
