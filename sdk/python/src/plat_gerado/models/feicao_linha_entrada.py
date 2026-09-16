from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicao_linha_entrada_atributos import FeicaoLinhaEntradaAtributos


T = TypeVar("T", bound="FeicaoLinhaEntrada")


@_attrs_define
class FeicaoLinhaEntrada:
    """
    Attributes:
        tipo_codigo (int):
        grupo (str):
        coordenadas (list[list[float]]):
        fase_bitmask (int | None | Unset):
        atributos (FeicaoLinhaEntradaAtributos | Unset):
    """

    tipo_codigo: int
    grupo: str
    coordenadas: list[list[float]]
    fase_bitmask: int | None | Unset = UNSET
    atributos: FeicaoLinhaEntradaAtributos | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_codigo = self.tipo_codigo

        grupo = self.grupo

        coordenadas = []
        for coordenadas_item_data in self.coordenadas:
            coordenadas_item = []
            for coordenadas_item_item_data in coordenadas_item_data:
                coordenadas_item_item: float
                coordenadas_item_item = coordenadas_item_item_data
                coordenadas_item.append(coordenadas_item_item)

            coordenadas.append(coordenadas_item)

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
                "coordenadas": coordenadas,
            }
        )
        if fase_bitmask is not UNSET:
            field_dict["fase_bitmask"] = fase_bitmask
        if atributos is not UNSET:
            field_dict["atributos"] = atributos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicao_linha_entrada_atributos import FeicaoLinhaEntradaAtributos  # noqa: PLC0415

        d = dict(src_dict)
        tipo_codigo = d.pop("tipo_codigo")

        grupo = d.pop("grupo")

        coordenadas = []
        _coordenadas = d.pop("coordenadas")
        for coordenadas_item_data in _coordenadas:
            coordenadas_item = []
            _coordenadas_item = coordenadas_item_data
            for coordenadas_item_item_data in _coordenadas_item:

                def _parse_coordenadas_item_item(data: object) -> float:
                    return cast(float, data)

                coordenadas_item_item = _parse_coordenadas_item_item(coordenadas_item_item_data)

                coordenadas_item.append(coordenadas_item_item)

            coordenadas.append(coordenadas_item)

        def _parse_fase_bitmask(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fase_bitmask = _parse_fase_bitmask(d.pop("fase_bitmask", UNSET))

        _atributos = d.pop("atributos", UNSET)
        atributos: FeicaoLinhaEntradaAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = FeicaoLinhaEntradaAtributos.from_dict(_atributos)

        feicao_linha_entrada = cls(
            tipo_codigo=tipo_codigo,
            grupo=grupo,
            coordenadas=coordenadas,
            fase_bitmask=fase_bitmask,
            atributos=atributos,
        )

        feicao_linha_entrada.additional_properties = d
        return feicao_linha_entrada

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
