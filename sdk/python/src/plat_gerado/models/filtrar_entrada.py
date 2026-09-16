from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.filtrar_entrada_filtro import FiltrarEntradaFiltro


T = TypeVar("T", bound="FiltrarEntrada")


@_attrs_define
class FiltrarEntrada:
    """
    Attributes:
        filtro (FiltrarEntradaFiltro):
        limite_amostra (int | Unset):  Default: 5000.
    """

    filtro: FiltrarEntradaFiltro
    limite_amostra: int | Unset = 5000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        filtro = self.filtro.to_dict()

        limite_amostra = self.limite_amostra

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "filtro": filtro,
            }
        )
        if limite_amostra is not UNSET:
            field_dict["limite_amostra"] = limite_amostra

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.filtrar_entrada_filtro import FiltrarEntradaFiltro  # noqa: PLC0415

        d = dict(src_dict)
        filtro = FiltrarEntradaFiltro.from_dict(d.pop("filtro"))

        limite_amostra = d.pop("limite_amostra", UNSET)

        filtrar_entrada = cls(
            filtro=filtro,
            limite_amostra=limite_amostra,
        )

        filtrar_entrada.additional_properties = d
        return filtrar_entrada

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
