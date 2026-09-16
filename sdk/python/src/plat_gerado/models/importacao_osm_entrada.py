from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.municipio_geo_json import MunicipioGeoJson


T = TypeVar("T", bound="ImportacaoOsmEntrada")


@_attrs_define
class ImportacaoOsmEntrada:
    """
    Attributes:
        caminho (str):
        municipio (MunicipioGeoJson): Polígono do recorte territorial em GeoJSON (EPSG:4326). Aceita Geometry, Feature
            ou
            FeatureCollection tal como vem da fonte (ex.: malha municipal do IBGE) — os campos extras
            (`geometry`, `features`, `properties`) passam intactos para o conector, que decide a forma.
        nome_municipio (str):
    """

    caminho: str
    municipio: MunicipioGeoJson
    nome_municipio: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        caminho = self.caminho

        municipio = self.municipio.to_dict()

        nome_municipio = self.nome_municipio

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "caminho": caminho,
                "municipio": municipio,
                "nome_municipio": nome_municipio,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.municipio_geo_json import MunicipioGeoJson  # noqa: PLC0415

        d = dict(src_dict)
        caminho = d.pop("caminho")

        municipio = MunicipioGeoJson.from_dict(d.pop("municipio"))

        nome_municipio = d.pop("nome_municipio")

        importacao_osm_entrada = cls(
            caminho=caminho,
            municipio=municipio,
            nome_municipio=nome_municipio,
        )

        importacao_osm_entrada.additional_properties = d
        return importacao_osm_entrada

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
