from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoRota")


@_attrs_define
class PedidoRota:
    """
    Attributes:
        origem (list[float]):
        destino (list[float]):
        perfil (Literal['carro'] | Unset):  Default: 'carro'.
    """

    origem: list[float]
    destino: list[float]
    perfil: Literal["carro"] | Unset = "carro"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        origem = self.origem

        destino = self.destino

        perfil = self.perfil

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "origem": origem,
                "destino": destino,
            }
        )
        if perfil is not UNSET:
            field_dict["perfil"] = perfil

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        origem = cast(list[float], d.pop("origem"))

        destino = cast(list[float], d.pop("destino"))

        perfil = cast(Literal["carro"] | Unset, d.pop("perfil", UNSET))
        if perfil != "carro" and not isinstance(perfil, Unset):
            raise ValueError(f"perfil must match const 'carro', got '{perfil}'")

        pedido_rota = cls(
            origem=origem,
            destino=destino,
            perfil=perfil,
        )

        pedido_rota.additional_properties = d
        return pedido_rota

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
