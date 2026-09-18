from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previsao_entrada_transformacao import PrevisaoEntradaTransformacao


T = TypeVar("T", bound="PrevisaoEntrada")


@_attrs_define
class PrevisaoEntrada:
    """
    Attributes:
        transformacao (PrevisaoEntradaTransformacao):
        valores (list[float | None]):
        bins (int | Unset):  Default: 30.
    """

    transformacao: PrevisaoEntradaTransformacao
    valores: list[float | None]
    bins: int | Unset = 30
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        transformacao = self.transformacao.to_dict()

        valores = []
        for valores_item_data in self.valores:
            valores_item: float | None
            valores_item = valores_item_data
            valores.append(valores_item)

        bins = self.bins

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "transformacao": transformacao,
                "valores": valores,
            }
        )
        if bins is not UNSET:
            field_dict["bins"] = bins

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previsao_entrada_transformacao import PrevisaoEntradaTransformacao  # noqa: PLC0415

        d = dict(src_dict)
        transformacao = PrevisaoEntradaTransformacao.from_dict(d.pop("transformacao"))

        valores = []
        _valores = d.pop("valores")
        for valores_item_data in _valores:

            def _parse_valores_item(data: object) -> float | None:
                if data is None:
                    return data
                return cast(float | None, data)

            valores_item = _parse_valores_item(valores_item_data)

            valores.append(valores_item)

        bins = d.pop("bins", UNSET)

        previsao_entrada = cls(
            transformacao=transformacao,
            valores=valores,
            bins=bins,
        )

        previsao_entrada.additional_properties = d
        return previsao_entrada

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
