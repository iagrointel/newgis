from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.conjunto_entrada_amc_area_estudo_type_0 import ConjuntoEntradaAmcAreaEstudoType0
    from ..models.conjunto_entrada_amc_feicoes_type_0 import ConjuntoEntradaAmcFeicoesType0


T = TypeVar("T", bound="ConjuntoEntradaAmc")


@_attrs_define
class ConjuntoEntradaAmc:
    """
    Attributes:
        nome (str):
        tipo (str): hexagonal, quadrada ou feicoes
        lado_m (float | None | Unset):
        area_estudo (ConjuntoEntradaAmcAreaEstudoType0 | None | Unset): Polygon/MultiPolygon GeoJSON em EPSG:4326
            (grade)
        feicoes (ConjuntoEntradaAmcFeicoesType0 | None | Unset): FeatureCollection GeoJSON em EPSG:4326 (tipo 'feicoes')
        campo_id (None | str | Unset): propriedade que carrega o id da unidade; sem ela, usa feature.id
    """

    nome: str
    tipo: str
    lado_m: float | None | Unset = UNSET
    area_estudo: ConjuntoEntradaAmcAreaEstudoType0 | None | Unset = UNSET
    feicoes: ConjuntoEntradaAmcFeicoesType0 | None | Unset = UNSET
    campo_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.conjunto_entrada_amc_area_estudo_type_0 import ConjuntoEntradaAmcAreaEstudoType0  # noqa: PLC0415
        from ..models.conjunto_entrada_amc_feicoes_type_0 import ConjuntoEntradaAmcFeicoesType0  # noqa: PLC0415

        nome = self.nome

        tipo = self.tipo

        lado_m: float | None | Unset
        if isinstance(self.lado_m, Unset):
            lado_m = UNSET
        else:
            lado_m = self.lado_m

        area_estudo: dict[str, Any] | None | Unset
        if isinstance(self.area_estudo, Unset):
            area_estudo = UNSET
        elif isinstance(self.area_estudo, ConjuntoEntradaAmcAreaEstudoType0):
            area_estudo = self.area_estudo.to_dict()
        else:
            area_estudo = self.area_estudo

        feicoes: dict[str, Any] | None | Unset
        if isinstance(self.feicoes, Unset):
            feicoes = UNSET
        elif isinstance(self.feicoes, ConjuntoEntradaAmcFeicoesType0):
            feicoes = self.feicoes.to_dict()
        else:
            feicoes = self.feicoes

        campo_id: None | str | Unset
        if isinstance(self.campo_id, Unset):
            campo_id = UNSET
        else:
            campo_id = self.campo_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nome": nome,
                "tipo": tipo,
            }
        )
        if lado_m is not UNSET:
            field_dict["lado_m"] = lado_m
        if area_estudo is not UNSET:
            field_dict["area_estudo"] = area_estudo
        if feicoes is not UNSET:
            field_dict["feicoes"] = feicoes
        if campo_id is not UNSET:
            field_dict["campo_id"] = campo_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conjunto_entrada_amc_area_estudo_type_0 import ConjuntoEntradaAmcAreaEstudoType0  # noqa: PLC0415
        from ..models.conjunto_entrada_amc_feicoes_type_0 import ConjuntoEntradaAmcFeicoesType0  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        tipo = d.pop("tipo")

        def _parse_lado_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        lado_m = _parse_lado_m(d.pop("lado_m", UNSET))

        def _parse_area_estudo(data: object) -> ConjuntoEntradaAmcAreaEstudoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                area_estudo_type_0 = ConjuntoEntradaAmcAreaEstudoType0.from_dict(data)

                return area_estudo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConjuntoEntradaAmcAreaEstudoType0 | None | Unset, data)

        area_estudo = _parse_area_estudo(d.pop("area_estudo", UNSET))

        def _parse_feicoes(data: object) -> ConjuntoEntradaAmcFeicoesType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                feicoes_type_0 = ConjuntoEntradaAmcFeicoesType0.from_dict(data)

                return feicoes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConjuntoEntradaAmcFeicoesType0 | None | Unset, data)

        feicoes = _parse_feicoes(d.pop("feicoes", UNSET))

        def _parse_campo_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        campo_id = _parse_campo_id(d.pop("campo_id", UNSET))

        conjunto_entrada_amc = cls(
            nome=nome,
            tipo=tipo,
            lado_m=lado_m,
            area_estudo=area_estudo,
            feicoes=feicoes,
            campo_id=campo_id,
        )

        conjunto_entrada_amc.additional_properties = d
        return conjunto_entrada_amc

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
