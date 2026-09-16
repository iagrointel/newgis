from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.conferencia_pressao_problemas_item import ConferenciaPressaoProblemasItem
    from ..models.conferencia_pressao_tiers_item import ConferenciaPressaoTiersItem


T = TypeVar("T", bound="ConferenciaPressao")


@_attrs_define
class ConferenciaPressao:
    """
    Attributes:
        controladores (int):
        controladores_conformes (int):
        transicoes_sem_regulador (int):
        tolerancia_m (float):
        tiers (list[ConferenciaPressaoTiersItem]):
        alterou_a_rede (bool):
        problemas (list[ConferenciaPressaoProblemasItem]):
    """

    controladores: int
    controladores_conformes: int
    transicoes_sem_regulador: int
    tolerancia_m: float
    tiers: list[ConferenciaPressaoTiersItem]
    alterou_a_rede: bool
    problemas: list[ConferenciaPressaoProblemasItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        controladores = self.controladores

        controladores_conformes = self.controladores_conformes

        transicoes_sem_regulador = self.transicoes_sem_regulador

        tolerancia_m = self.tolerancia_m

        tiers = []
        for tiers_item_data in self.tiers:
            tiers_item = tiers_item_data.to_dict()
            tiers.append(tiers_item)

        alterou_a_rede = self.alterou_a_rede

        problemas = []
        for problemas_item_data in self.problemas:
            problemas_item = problemas_item_data.to_dict()
            problemas.append(problemas_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "controladores": controladores,
                "controladores_conformes": controladores_conformes,
                "transicoes_sem_regulador": transicoes_sem_regulador,
                "tolerancia_m": tolerancia_m,
                "tiers": tiers,
                "alterou_a_rede": alterou_a_rede,
                "problemas": problemas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.conferencia_pressao_problemas_item import ConferenciaPressaoProblemasItem  # noqa: PLC0415
        from ..models.conferencia_pressao_tiers_item import ConferenciaPressaoTiersItem  # noqa: PLC0415

        d = dict(src_dict)
        controladores = d.pop("controladores")

        controladores_conformes = d.pop("controladores_conformes")

        transicoes_sem_regulador = d.pop("transicoes_sem_regulador")

        tolerancia_m = d.pop("tolerancia_m")

        tiers = []
        _tiers = d.pop("tiers")
        for tiers_item_data in _tiers:
            tiers_item = ConferenciaPressaoTiersItem.from_dict(tiers_item_data)

            tiers.append(tiers_item)

        alterou_a_rede = d.pop("alterou_a_rede")

        problemas = []
        _problemas = d.pop("problemas")
        for problemas_item_data in _problemas:
            problemas_item = ConferenciaPressaoProblemasItem.from_dict(problemas_item_data)

            problemas.append(problemas_item)

        conferencia_pressao = cls(
            controladores=controladores,
            controladores_conformes=controladores_conformes,
            transicoes_sem_regulador=transicoes_sem_regulador,
            tolerancia_m=tolerancia_m,
            tiers=tiers,
            alterou_a_rede=alterou_a_rede,
            problemas=problemas,
        )

        conferencia_pressao.additional_properties = d
        return conferencia_pressao

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
