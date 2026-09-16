from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.evento_saida_atributos import EventoSaidaAtributos


T = TypeVar("T", bound="EventoSaida")


@_attrs_define
class EventoSaida:
    """
    Attributes:
        tempo_evento (str):
        recebido_em (str):
        atributos (EventoSaidaAtributos):
        rastro_id (None | str | Unset):
        lon (float | None | Unset):
        lat (float | None | Unset):
    """

    tempo_evento: str
    recebido_em: str
    atributos: EventoSaidaAtributos
    rastro_id: None | str | Unset = UNSET
    lon: float | None | Unset = UNSET
    lat: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tempo_evento = self.tempo_evento

        recebido_em = self.recebido_em

        atributos = self.atributos.to_dict()

        rastro_id: None | str | Unset
        if isinstance(self.rastro_id, Unset):
            rastro_id = UNSET
        else:
            rastro_id = self.rastro_id

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tempo_evento": tempo_evento,
                "recebido_em": recebido_em,
                "atributos": atributos,
            }
        )
        if rastro_id is not UNSET:
            field_dict["rastro_id"] = rastro_id
        if lon is not UNSET:
            field_dict["lon"] = lon
        if lat is not UNSET:
            field_dict["lat"] = lat

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.evento_saida_atributos import EventoSaidaAtributos  # noqa: PLC0415

        d = dict(src_dict)
        tempo_evento = d.pop("tempo_evento")

        recebido_em = d.pop("recebido_em")

        atributos = EventoSaidaAtributos.from_dict(d.pop("atributos"))

        def _parse_rastro_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rastro_id = _parse_rastro_id(d.pop("rastro_id", UNSET))

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

        evento_saida = cls(
            tempo_evento=tempo_evento,
            recebido_em=recebido_em,
            atributos=atributos,
            rastro_id=rastro_id,
            lon=lon,
            lat=lat,
        )

        evento_saida.additional_properties = d
        return evento_saida

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
