from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.acervo_feicoes_features_item import AcervoFeicoesFeaturesItem


T = TypeVar("T", bound="AcervoFeicoes")


@_attrs_define
class AcervoFeicoes:
    """GeoJSON de uma camada publicada. `features` fica vazio quando o filtro não achou nada — nunca quando
    falta assinatura: aí a rota já devolveu 403 antes de consultar.

        Attributes:
            type_ (str):
            camada (str):
            total (int):
            features (list[AcervoFeicoesFeaturesItem]):
    """

    type_: str
    camada: str
    total: int
    features: list[AcervoFeicoesFeaturesItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        camada = self.camada

        total = self.total

        features = []
        for features_item_data in self.features:
            features_item = features_item_data.to_dict()
            features.append(features_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "camada": camada,
                "total": total,
                "features": features,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acervo_feicoes_features_item import AcervoFeicoesFeaturesItem  # noqa: PLC0415

        d = dict(src_dict)
        type_ = d.pop("type")

        camada = d.pop("camada")

        total = d.pop("total")

        features = []
        _features = d.pop("features")
        for features_item_data in _features:
            features_item = AcervoFeicoesFeaturesItem.from_dict(features_item_data)

            features.append(features_item)

        acervo_feicoes = cls(
            type_=type_,
            camada=camada,
            total=total,
            features=features,
        )

        acervo_feicoes.additional_properties = d
        return acervo_feicoes

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
