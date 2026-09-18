from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.feicoes_saida_conexao_features_item import FeicoesSaidaConexaoFeaturesItem


T = TypeVar("T", bound="FeicoesSaidaConexao")


@_attrs_define
class FeicoesSaidaConexao:
    """GeoJSON + o que a paginação apurou. `numero_matched` é o total DECLARADO pelo serviço (pode ser None:
    nem todo serviço declara) e `numberReturned` é o que veio nesta resposta — os dois juntos, nunca um só.

        Attributes:
            features (list[FeicoesSaidaConexaoFeaturesItem]):
            number_returned (int):
            colecao (str):
            srid_entregue (int):
            type_ (str | Unset):  Default: 'FeatureCollection'.
            number_matched (int | None | Unset):
            do_cache (bool | Unset):  Default: False.
            avisos (list[str] | Unset):
    """

    features: list[FeicoesSaidaConexaoFeaturesItem]
    number_returned: int
    colecao: str
    srid_entregue: int
    type_: str | Unset = "FeatureCollection"
    number_matched: int | None | Unset = UNSET
    do_cache: bool | Unset = False
    avisos: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        features = []
        for features_item_data in self.features:
            features_item = features_item_data.to_dict()
            features.append(features_item)

        number_returned = self.number_returned

        colecao = self.colecao

        srid_entregue = self.srid_entregue

        type_ = self.type_

        number_matched: int | None | Unset
        if isinstance(self.number_matched, Unset):
            number_matched = UNSET
        else:
            number_matched = self.number_matched

        do_cache = self.do_cache

        avisos: list[str] | Unset = UNSET
        if not isinstance(self.avisos, Unset):
            avisos = self.avisos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "features": features,
                "numberReturned": number_returned,
                "colecao": colecao,
                "srid_entregue": srid_entregue,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_
        if number_matched is not UNSET:
            field_dict["numberMatched"] = number_matched
        if do_cache is not UNSET:
            field_dict["do_cache"] = do_cache
        if avisos is not UNSET:
            field_dict["avisos"] = avisos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.feicoes_saida_conexao_features_item import FeicoesSaidaConexaoFeaturesItem  # noqa: PLC0415

        d = dict(src_dict)
        features = []
        _features = d.pop("features")
        for features_item_data in _features:
            features_item = FeicoesSaidaConexaoFeaturesItem.from_dict(features_item_data)

            features.append(features_item)

        number_returned = d.pop("numberReturned")

        colecao = d.pop("colecao")

        srid_entregue = d.pop("srid_entregue")

        type_ = d.pop("type", UNSET)

        def _parse_number_matched(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        number_matched = _parse_number_matched(d.pop("numberMatched", UNSET))

        do_cache = d.pop("do_cache", UNSET)

        avisos = cast(list[str], d.pop("avisos", UNSET))

        feicoes_saida_conexao = cls(
            features=features,
            number_returned=number_returned,
            colecao=colecao,
            srid_entregue=srid_entregue,
            type_=type_,
            number_matched=number_matched,
            do_cache=do_cache,
            avisos=avisos,
        )

        feicoes_saida_conexao.additional_properties = d
        return feicoes_saida_conexao

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
