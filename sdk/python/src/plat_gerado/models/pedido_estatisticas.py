from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoEstatisticas")


@_attrs_define
class PedidoEstatisticas:
    """
    Attributes:
        busca (None | str | Unset):
        bbox (list[float] | None | Unset): extensão do mapa em WGS84: [oeste, sul, leste, norte]
        fids (list[int] | None | Unset): seleção vinda do mapa: valores da chave primária
        colunas (list[str] | None | Unset):
    """

    busca: None | str | Unset = UNSET
    bbox: list[float] | None | Unset = UNSET
    fids: list[int] | None | Unset = UNSET
    colunas: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        busca: None | str | Unset
        if isinstance(self.busca, Unset):
            busca = UNSET
        else:
            busca = self.busca

        bbox: list[float] | None | Unset
        if isinstance(self.bbox, Unset):
            bbox = UNSET
        elif isinstance(self.bbox, list):
            bbox = self.bbox

        else:
            bbox = self.bbox

        fids: list[int] | None | Unset
        if isinstance(self.fids, Unset):
            fids = UNSET
        elif isinstance(self.fids, list):
            fids = self.fids

        else:
            fids = self.fids

        colunas: list[str] | None | Unset
        if isinstance(self.colunas, Unset):
            colunas = UNSET
        elif isinstance(self.colunas, list):
            colunas = self.colunas

        else:
            colunas = self.colunas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if busca is not UNSET:
            field_dict["busca"] = busca
        if bbox is not UNSET:
            field_dict["bbox"] = bbox
        if fids is not UNSET:
            field_dict["fids"] = fids
        if colunas is not UNSET:
            field_dict["colunas"] = colunas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_busca(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        busca = _parse_busca(d.pop("busca", UNSET))

        def _parse_bbox(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                bbox_type_0 = cast(list[float], data)

                return bbox_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        bbox = _parse_bbox(d.pop("bbox", UNSET))

        def _parse_fids(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                fids_type_0 = cast(list[int], data)

                return fids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        fids = _parse_fids(d.pop("fids", UNSET))

        def _parse_colunas(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                colunas_type_0 = cast(list[str], data)

                return colunas_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        colunas = _parse_colunas(d.pop("colunas", UNSET))

        pedido_estatisticas = cls(
            busca=busca,
            bbox=bbox,
            fids=fids,
            colunas=colunas,
        )

        pedido_estatisticas.additional_properties = d
        return pedido_estatisticas

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
