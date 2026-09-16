from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.conjunto_entrada_area import ConjuntoEntradaArea


T = TypeVar("T", bound="ConjuntoEntrada")


@_attrs_define
class ConjuntoEntrada:
    """
    Attributes:
        nome (str):
        area (ConjuntoEntradaArea): polígono GeoJSON (Polygon) em EPSG:4326
    """

    nome: str
    area: ConjuntoEntradaArea

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        area = self.area.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "area": area,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conjunto_entrada_area import ConjuntoEntradaArea  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        area = ConjuntoEntradaArea.from_dict(d.pop("area"))

        conjunto_entrada = cls(
            nome=nome,
            area=area,
        )

        return conjunto_entrada
