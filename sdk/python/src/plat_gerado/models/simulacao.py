from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.simulacao_atributos import SimulacaoAtributos


T = TypeVar("T", bound="Simulacao")


@_attrs_define
class Simulacao:
    """Resultado de POST /api/fluxos/{id}/simular: o que o mapeamento e o filtro fazem com um registro de
    exemplo, SEM gravar nada. É como se confere fuso e filtro antes de ligar a fonte.

        Attributes:
            aceito (bool):
            motivo (None | str | Unset):
            rastro_id (None | str | Unset):
            tempo_evento (None | str | Unset):
            lon (float | None | Unset):
            lat (float | None | Unset):
            atributos (SimulacaoAtributos | Unset):
    """

    aceito: bool
    motivo: None | str | Unset = UNSET
    rastro_id: None | str | Unset = UNSET
    tempo_evento: None | str | Unset = UNSET
    lon: float | None | Unset = UNSET
    lat: float | None | Unset = UNSET
    atributos: SimulacaoAtributos | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aceito = self.aceito

        motivo: None | str | Unset
        if isinstance(self.motivo, Unset):
            motivo = UNSET
        else:
            motivo = self.motivo

        rastro_id: None | str | Unset
        if isinstance(self.rastro_id, Unset):
            rastro_id = UNSET
        else:
            rastro_id = self.rastro_id

        tempo_evento: None | str | Unset
        if isinstance(self.tempo_evento, Unset):
            tempo_evento = UNSET
        else:
            tempo_evento = self.tempo_evento

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

        atributos: dict[str, Any] | Unset = UNSET
        if not isinstance(self.atributos, Unset):
            atributos = self.atributos.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aceito": aceito,
            }
        )
        if motivo is not UNSET:
            field_dict["motivo"] = motivo
        if rastro_id is not UNSET:
            field_dict["rastro_id"] = rastro_id
        if tempo_evento is not UNSET:
            field_dict["tempo_evento"] = tempo_evento
        if lon is not UNSET:
            field_dict["lon"] = lon
        if lat is not UNSET:
            field_dict["lat"] = lat
        if atributos is not UNSET:
            field_dict["atributos"] = atributos

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.simulacao_atributos import SimulacaoAtributos  # noqa: PLC0415

        d = dict(src_dict)
        aceito = d.pop("aceito")

        def _parse_motivo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        motivo = _parse_motivo(d.pop("motivo", UNSET))

        def _parse_rastro_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rastro_id = _parse_rastro_id(d.pop("rastro_id", UNSET))

        def _parse_tempo_evento(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tempo_evento = _parse_tempo_evento(d.pop("tempo_evento", UNSET))

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

        _atributos = d.pop("atributos", UNSET)
        atributos: SimulacaoAtributos | Unset
        if isinstance(_atributos, Unset):
            atributos = UNSET
        else:
            atributos = SimulacaoAtributos.from_dict(_atributos)

        simulacao = cls(
            aceito=aceito,
            motivo=motivo,
            rastro_id=rastro_id,
            tempo_evento=tempo_evento,
            lon=lon,
            lat=lat,
            atributos=atributos,
        )

        simulacao.additional_properties = d
        return simulacao

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
