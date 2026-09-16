from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoLinhas")


@_attrs_define
class PedidoLinhas:
    """
    Attributes:
        busca (None | str | Unset):
        bbox (list[float] | None | Unset): extensão do mapa em WGS84: [oeste, sul, leste, norte]
        fids (list[int] | None | Unset): seleção vinda do mapa: valores da chave primária
        pagina (int | Unset):  Default: 1.
        por_pagina (int | Unset):  Default: 50.
        ordenar_por (None | str | Unset):
        ordem (str | Unset):  Default: 'asc'.
        geometria (bool | Unset): devolve a geometria em GeoJSON 4326 para o mapa desenhar Default: False.
        contar (bool | Unset): conta o total sob o mesmo filtro; false devolve total nulo Default: True.
    """

    busca: None | str | Unset = UNSET
    bbox: list[float] | None | Unset = UNSET
    fids: list[int] | None | Unset = UNSET
    pagina: int | Unset = 1
    por_pagina: int | Unset = 50
    ordenar_por: None | str | Unset = UNSET
    ordem: str | Unset = "asc"
    geometria: bool | Unset = False
    contar: bool | Unset = True
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

        pagina = self.pagina

        por_pagina = self.por_pagina

        ordenar_por: None | str | Unset
        if isinstance(self.ordenar_por, Unset):
            ordenar_por = UNSET
        else:
            ordenar_por = self.ordenar_por

        ordem = self.ordem

        geometria = self.geometria

        contar = self.contar

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if busca is not UNSET:
            field_dict["busca"] = busca
        if bbox is not UNSET:
            field_dict["bbox"] = bbox
        if fids is not UNSET:
            field_dict["fids"] = fids
        if pagina is not UNSET:
            field_dict["pagina"] = pagina
        if por_pagina is not UNSET:
            field_dict["por_pagina"] = por_pagina
        if ordenar_por is not UNSET:
            field_dict["ordenar_por"] = ordenar_por
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if geometria is not UNSET:
            field_dict["geometria"] = geometria
        if contar is not UNSET:
            field_dict["contar"] = contar

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

        pagina = d.pop("pagina", UNSET)

        por_pagina = d.pop("por_pagina", UNSET)

        def _parse_ordenar_por(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ordenar_por = _parse_ordenar_por(d.pop("ordenar_por", UNSET))

        ordem = d.pop("ordem", UNSET)

        geometria = d.pop("geometria", UNSET)

        contar = d.pop("contar", UNSET)

        pedido_linhas = cls(
            busca=busca,
            bbox=bbox,
            fids=fids,
            pagina=pagina,
            por_pagina=por_pagina,
            ordenar_por=ordenar_por,
            ordem=ordem,
            geometria=geometria,
            contar=contar,
        )

        pedido_linhas.additional_properties = d
        return pedido_linhas

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
