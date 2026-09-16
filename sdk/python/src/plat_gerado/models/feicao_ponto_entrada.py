from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_ponto_entrada_atributos import FeicaoPontoEntradaAtributos


T = TypeVar("T", bound="FeicaoPontoEntrada")


@_attrs_define
class FeicaoPontoEntrada:
    """
    Attributes:
        tipo_codigo (int):
        grupo (str):
        lon (float):
        lat (float):
        fase_bitmask (int | None | Unset):
        atributos (FeicaoPontoEntradaAtributos | Unset):
    """

    tipo_codigo: int
    grupo: str
    lon: float
    lat: float
    fase_bitmask: int | None | Unset = UNSET
    atributos: FeicaoPontoEntradaAtributos | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_codigo = self.tipo_codigo

        grupo = self.grupo

        lon = self.lon

        lat = self.lat

        fase_bitmask: int | None | Unset
        if isinstance(self.fase_bitmask, Unset):
            fase_bitmask = UNSET
        else:
            fase_bitmask = self.fase_bitmask

        atributos: dict[str, Any] | Unset = UNSET
        if not isinstance(self.atributos, Unset):
            atributos = self.atributos.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo_codigo": tipo_codigo,
                "grupo": grupo,
                "lon": lon,
                "lat": lat,
            }
        )
        if fase_bitmask is not UNSET:
            field_dict["fase_bitmask"] = fase_bitmask
        if atributos is not UNSET:
            field_dict["atributos"] = atributos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_ponto_entrada_atributos import FeicaoPontoEntradaAtributos  # noqa: PLC0415

        d = dict(src_dict)
        tipo_codigo = d.pop("tipo_codigo")

        grupo = d.pop("grupo")

        lon = d.pop("lon")

        lat = d.pop("lat")

        def _parse_fase_bitmask(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fase_bitmask = _parse_fase_bitmask(d.pop("fase_bitmask", UNSET))

        _atributos = d.pop("atributos", UNSET)
        atributos: FeicaoPontoEntradaAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = FeicaoPontoEntradaAtributos.from_dict(_atributos)

        feicao_ponto_entrada = cls(
            tipo_codigo=tipo_codigo,
            grupo=grupo,
            lon=lon,
            lat=lat,
            fase_bitmask=fase_bitmask,
            atributos=atributos,
        )

        feicao_ponto_entrada.additional_properties = d
        return feicao_ponto_entrada

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
