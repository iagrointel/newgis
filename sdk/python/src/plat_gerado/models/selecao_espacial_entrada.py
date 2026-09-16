from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SelecaoEspacialEntrada")


@_attrs_define
class SelecaoEspacialEntrada:
    """
    Attributes:
        camada_a (str):
        camada_b (str):
        relacao (str | Unset):  Default: 'intersects'.
        distancia_m (float | None | Unset):
        limite_amostra (int | Unset):  Default: 5000.
    """

    camada_a: str
    camada_b: str
    relacao: str | Unset = "intersects"
    distancia_m: float | None | Unset = UNSET
    limite_amostra: int | Unset = 5000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camada_a = self.camada_a

        camada_b = self.camada_b

        relacao = self.relacao

        distancia_m: float | None | Unset
        if isinstance(self.distancia_m, Unset):
            distancia_m = UNSET
        else:
            distancia_m = self.distancia_m

        limite_amostra = self.limite_amostra

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada_a": camada_a,
                "camada_b": camada_b,
            }
        )
        if relacao is not UNSET:
            field_dict["relacao"] = relacao
        if distancia_m is not UNSET:
            field_dict["distancia_m"] = distancia_m
        if limite_amostra is not UNSET:
            field_dict["limite_amostra"] = limite_amostra

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        camada_a = d.pop("camada_a")

        camada_b = d.pop("camada_b")

        relacao = d.pop("relacao", UNSET)

        def _parse_distancia_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distancia_m = _parse_distancia_m(d.pop("distancia_m", UNSET))

        limite_amostra = d.pop("limite_amostra", UNSET)

        selecao_espacial_entrada = cls(
            camada_a=camada_a,
            camada_b=camada_b,
            relacao=relacao,
            distancia_m=distancia_m,
            limite_amostra=limite_amostra,
        )

        selecao_espacial_entrada.additional_properties = d
        return selecao_espacial_entrada

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
