from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.selecionar_entrada_geometria import SelecionarEntradaGeometria


T = TypeVar("T", bound="SelecionarEntrada")


@_attrs_define
class SelecionarEntrada:
    """
    Attributes:
        geometria (SelecionarEntradaGeometria):
        relacao (str | Unset):  Default: 'intersects'.
        distancia_m (float | None | Unset):
        modo (str | Unset):  Default: 'novo'.
        ids_atuais (list[Any] | Unset):
        limite_amostra (int | Unset):  Default: 5000.
    """

    geometria: SelecionarEntradaGeometria
    relacao: str | Unset = "intersects"
    distancia_m: float | None | Unset = UNSET
    modo: str | Unset = "novo"
    ids_atuais: list[Any] | Unset = UNSET
    limite_amostra: int | Unset = 5000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        geometria = self.geometria.to_dict()

        relacao = self.relacao

        distancia_m: float | None | Unset
        if isinstance(self.distancia_m, Unset):
            distancia_m = UNSET
        else:
            distancia_m = self.distancia_m

        modo = self.modo

        ids_atuais: list[Any] | Unset = UNSET
        if not isinstance(self.ids_atuais, Unset):
            ids_atuais = self.ids_atuais

        limite_amostra = self.limite_amostra

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "geometria": geometria,
            }
        )
        if relacao is not UNSET:
            field_dict["relacao"] = relacao
        if distancia_m is not UNSET:
            field_dict["distancia_m"] = distancia_m
        if modo is not UNSET:
            field_dict["modo"] = modo
        if ids_atuais is not UNSET:
            field_dict["ids_atuais"] = ids_atuais
        if limite_amostra is not UNSET:
            field_dict["limite_amostra"] = limite_amostra

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.selecionar_entrada_geometria import SelecionarEntradaGeometria  # noqa: PLC0415

        d = dict(src_dict)
        geometria = SelecionarEntradaGeometria.from_dict(d.pop("geometria"))

        relacao = d.pop("relacao", UNSET)

        def _parse_distancia_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distancia_m = _parse_distancia_m(d.pop("distancia_m", UNSET))

        modo = d.pop("modo", UNSET)

        ids_atuais = cast(list[Any], d.pop("ids_atuais", UNSET))

        limite_amostra = d.pop("limite_amostra", UNSET)

        selecionar_entrada = cls(
            geometria=geometria,
            relacao=relacao,
            distancia_m=distancia_m,
            modo=modo,
            ids_atuais=ids_atuais,
            limite_amostra=limite_amostra,
        )

        selecionar_entrada.additional_properties = d
        return selecionar_entrada

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
