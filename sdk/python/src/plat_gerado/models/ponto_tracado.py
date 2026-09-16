from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PontoTracado")


@_attrs_define
class PontoTracado:
    """Um ponto de partida ou barreira: por feição (`feicao_id` + `terminal`, obrigatório quando a feição tem
    mais de um terminal) OU por coordenada (`lon`/`lat`, com `tolerancia_m` própria ou a da rede).

        Attributes:
            feicao_id (None | str | Unset):
            terminal (int | None | Unset):
            lon (float | None | Unset):
            lat (float | None | Unset):
            tolerancia_m (float | None | Unset):
    """

    feicao_id: None | str | Unset = UNSET
    terminal: int | None | Unset = UNSET
    lon: float | None | Unset = UNSET
    lat: float | None | Unset = UNSET
    tolerancia_m: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feicao_id: None | str | Unset
        if isinstance(self.feicao_id, Unset):
            feicao_id = UNSET
        else:
            feicao_id = self.feicao_id

        terminal: int | None | Unset
        if isinstance(self.terminal, Unset):
            terminal = UNSET
        else:
            terminal = self.terminal

        lon: float | None | Unset
        if isinstance(self.lon, Unset):
            lon = UNSET
        else:
            lon = self.lon

        lat: float | None | Unset
        if isinstance(self.lat, Unset):
            lat = UNSET
        else:
            lat = self.lat

        tolerancia_m: float | None | Unset
        if isinstance(self.tolerancia_m, Unset):
            tolerancia_m = UNSET
        else:
            tolerancia_m = self.tolerancia_m

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if feicao_id is not UNSET:
            field_dict["feicao_id"] = feicao_id
        if terminal is not UNSET:
            field_dict["terminal"] = terminal
        if lon is not UNSET:
            field_dict["lon"] = lon
        if lat is not UNSET:
            field_dict["lat"] = lat
        if tolerancia_m is not UNSET:
            field_dict["tolerancia_m"] = tolerancia_m

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_feicao_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        feicao_id = _parse_feicao_id(d.pop("feicao_id", UNSET))

        def _parse_terminal(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        terminal = _parse_terminal(d.pop("terminal", UNSET))

        def _parse_lon(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        lon = _parse_lon(d.pop("lon", UNSET))

        def _parse_lat(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        lat = _parse_lat(d.pop("lat", UNSET))

        def _parse_tolerancia_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        tolerancia_m = _parse_tolerancia_m(d.pop("tolerancia_m", UNSET))

        ponto_tracado = cls(
            feicao_id=feicao_id,
            terminal=terminal,
            lon=lon,
            lat=lat,
            tolerancia_m=tolerancia_m,
        )

        ponto_tracado.additional_properties = d
        return ponto_tracado

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
