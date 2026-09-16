from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.pedido_transformar_tipo import PedidoTransformarTipo
from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoTransformar")


@_attrs_define
class PedidoTransformar:
    """
    Attributes:
        origem (int): código EPSG de origem
        destino (int): código EPSG de destino
        coordenadas (list[float]): [lon, lat] para ponto; [xmin, ymin, xmax, ymax] para bbox (na ordem do CRS de origem)
        tipo (PedidoTransformarTipo | Unset):  Default: PedidoTransformarTipo.PONTO.
    """

    origem: int
    destino: int
    coordenadas: list[float]
    tipo: PedidoTransformarTipo | Unset = PedidoTransformarTipo.PONTO
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        origem = self.origem

        destino = self.destino

        coordenadas = self.coordenadas

        tipo: str | Unset = UNSET
        if not isinstance(self.tipo, Unset):
            tipo = self.tipo.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "origem": origem,
                "destino": destino,
                "coordenadas": coordenadas,
            }
        )
        if tipo is not UNSET:
            field_dict["tipo"] = tipo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        origem = d.pop("origem")

        destino = d.pop("destino")

        coordenadas = cast(list[float], d.pop("coordenadas"))

        _tipo = d.pop("tipo", UNSET)
        tipo: PedidoTransformarTipo | Unset
        if isinstance(_tipo, Unset):
            tipo = UNSET
        else:
            tipo = PedidoTransformarTipo(_tipo)

        pedido_transformar = cls(
            origem=origem,
            destino=destino,
            coordenadas=coordenadas,
            tipo=tipo,
        )

        pedido_transformar.additional_properties = d
        return pedido_transformar

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
