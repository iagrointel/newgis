from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.elemento_tracado import ElementoTracado
    from ..models.tracado_resultado_geometria_type_0 import TracadoResultadoGeometriaType0


T = TypeVar("T", bound="TracadoResultado")


@_attrs_define
class TracadoResultado:
    """
    Attributes:
        tipo (str):
        elementos (list[ElementoTracado]):
        contagem (int):
        nos_alcancados (int):
        geometria (None | TracadoResultadoGeometriaType0):
        duracao_ms (int):
    """

    tipo: str
    elementos: list[ElementoTracado]
    contagem: int
    nos_alcancados: int
    geometria: None | TracadoResultadoGeometriaType0
    duracao_ms: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tracado_resultado_geometria_type_0 import TracadoResultadoGeometriaType0  # noqa: PLC0415

        tipo = self.tipo

        elementos = []
        for elementos_item_data in self.elementos:
            elementos_item = elementos_item_data.to_dict()
            elementos.append(elementos_item)

        contagem = self.contagem

        nos_alcancados = self.nos_alcancados

        geometria: dict[str, Any] | None
        if isinstance(self.geometria, TracadoResultadoGeometriaType0):
            geometria = self.geometria.to_dict()
        else:
            geometria = self.geometria

        duracao_ms = self.duracao_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo": tipo,
                "elementos": elementos,
                "contagem": contagem,
                "nos_alcancados": nos_alcancados,
                "geometria": geometria,
                "duracao_ms": duracao_ms,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.elemento_tracado import ElementoTracado  # noqa: PLC0415
        from ..models.tracado_resultado_geometria_type_0 import TracadoResultadoGeometriaType0  # noqa: PLC0415

        d = dict(src_dict)
        tipo = d.pop("tipo")

        elementos = []
        _elementos = d.pop("elementos")
        for elementos_item_data in _elementos:
            elementos_item = ElementoTracado.from_dict(elementos_item_data)

            elementos.append(elementos_item)

        contagem = d.pop("contagem")

        nos_alcancados = d.pop("nos_alcancados")

        def _parse_geometria(data: object) -> None | TracadoResultadoGeometriaType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                geometria_type_0 = TracadoResultadoGeometriaType0.from_dict(data)

                return geometria_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TracadoResultadoGeometriaType0, data)

        geometria = _parse_geometria(d.pop("geometria"))

        duracao_ms = d.pop("duracao_ms")

        tracado_resultado = cls(
            tipo=tipo,
            elementos=elementos,
            contagem=contagem,
            nos_alcancados=nos_alcancados,
            geometria=geometria,
            duracao_ms=duracao_ms,
        )

        tracado_resultado.additional_properties = d
        return tracado_resultado

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
