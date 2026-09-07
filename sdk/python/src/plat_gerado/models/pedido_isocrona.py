from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoIsocrona")


@_attrs_define
class PedidoIsocrona:
    """
    Attributes:
        ponto (list[float]):
        minutos (float):
        perfil (Literal['carro'] | Unset):  Default: 'carro'.
        ratio_casco (float | None | Unset):
    """

    ponto: list[float]
    minutos: float
    perfil: Literal["carro"] | Unset = "carro"
    ratio_casco: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ponto = self.ponto

        minutos = self.minutos

        perfil = self.perfil

        ratio_casco: float | None | Unset
        if isinstance(self.ratio_casco, Unset):
            ratio_casco = UNSET
        else:
            ratio_casco = self.ratio_casco

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ponto": ponto,
                "minutos": minutos,
            }
        )
        if perfil is not UNSET:
            field_dict["perfil"] = perfil
        if ratio_casco is not UNSET:
            field_dict["ratio_casco"] = ratio_casco

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ponto = cast(list[float], d.pop("ponto"))

        minutos = d.pop("minutos")

        perfil = cast(Literal["carro"] | Unset, d.pop("perfil", UNSET))
        if perfil != "carro" and not isinstance(perfil, Unset):
            raise ValueError(f"perfil must match const 'carro', got '{perfil}'")

        def _parse_ratio_casco(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        ratio_casco = _parse_ratio_casco(d.pop("ratio_casco", UNSET))

        pedido_isocrona = cls(
            ponto=ponto,
            minutos=minutos,
            perfil=perfil,
            ratio_casco=ratio_casco,
        )

        pedido_isocrona.additional_properties = d
        return pedido_isocrona

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
