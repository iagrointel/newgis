from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.solido_entrada_poligono import SolidoEntradaPoligono


T = TypeVar("T", bound="SolidoEntrada")


@_attrs_define
class SolidoEntrada:
    """
    Attributes:
        poligono (SolidoEntradaPoligono): GeoJSON Polygon no SRID declarado
        altura_m (float):
    """

    poligono: SolidoEntradaPoligono
    altura_m: float

    def to_dict(self) -> dict[str, Any]:
        poligono = self.poligono.to_dict()

        altura_m = self.altura_m

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "poligono": poligono,
                "altura_m": altura_m,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.solido_entrada_poligono import SolidoEntradaPoligono  # noqa: PLC0415

        d = dict(src_dict)
        poligono = SolidoEntradaPoligono.from_dict(d.pop("poligono"))

        altura_m = d.pop("altura_m")

        solido_entrada = cls(
            poligono=poligono,
            altura_m=altura_m,
        )

        return solido_entrada
