from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="Terreno")


@_attrs_define
class Terreno:
    """Grade de alturas do terreno, em SRID projetado (metros).

    Attributes:
        srid (int): SIRGAS 2000 UTM sul (31965-31985): zona do terreno
        x0 (float): oeste da grade, no SRID, em metros
        y0 (float): sul da grade, no SRID, em metros
        celula_m (float): lado da célula, em metros
        alturas (list[list[float]]): linhas de NORTE para SUL
    """

    srid: int
    x0: float
    y0: float
    celula_m: float
    alturas: list[list[float]]

    def to_dict(self) -> dict[str, Any]:
        srid = self.srid

        x0 = self.x0

        y0 = self.y0

        celula_m = self.celula_m

        alturas = []
        for alturas_item_data in self.alturas:
            alturas_item = alturas_item_data

            alturas.append(alturas_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "srid": srid,
                "x0": x0,
                "y0": y0,
                "celula_m": celula_m,
                "alturas": alturas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        srid = d.pop("srid")

        x0 = d.pop("x0")

        y0 = d.pop("y0")

        celula_m = d.pop("celula_m")

        alturas = []
        _alturas = d.pop("alturas")
        for alturas_item_data in _alturas:
            alturas_item = cast(list[float], alturas_item_data)

            alturas.append(alturas_item)

        terreno = cls(
            srid=srid,
            x0=x0,
            y0=y0,
            celula_m=celula_m,
            alturas=alturas,
        )

        return terreno
