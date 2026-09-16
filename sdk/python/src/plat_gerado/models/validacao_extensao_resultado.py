from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.validacao_extensao_resultado_erros_item import ValidacaoExtensaoResultadoErrosItem


T = TypeVar("T", bound="ValidacaoExtensaoResultado")


@_attrs_define
class ValidacaoExtensaoResultado:
    """
    Attributes:
        rede_id (str):
        versao_edicao (int):
        areas_processadas (int):
        areas_ativas_restantes (int):
        feicoes_em_escopo (int):
        feicoes_total (int):
        total_erros (int):
        erros (list[ValidacaoExtensaoResultadoErrosItem]):
        tempo_ms (float):
        carga_1min (float):
        ram_livre_gb (float):
        medido_em (str):
    """

    rede_id: str
    versao_edicao: int
    areas_processadas: int
    areas_ativas_restantes: int
    feicoes_em_escopo: int
    feicoes_total: int
    total_erros: int
    erros: list[ValidacaoExtensaoResultadoErrosItem]
    tempo_ms: float
    carga_1min: float
    ram_livre_gb: float
    medido_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        versao_edicao = self.versao_edicao

        areas_processadas = self.areas_processadas

        areas_ativas_restantes = self.areas_ativas_restantes

        feicoes_em_escopo = self.feicoes_em_escopo

        feicoes_total = self.feicoes_total

        total_erros = self.total_erros

        erros = []
        for erros_item_data in self.erros:
            erros_item = erros_item_data.to_dict()
            erros.append(erros_item)

        tempo_ms = self.tempo_ms

        carga_1min = self.carga_1min

        ram_livre_gb = self.ram_livre_gb

        medido_em = self.medido_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "versao_edicao": versao_edicao,
                "areas_processadas": areas_processadas,
                "areas_ativas_restantes": areas_ativas_restantes,
                "feicoes_em_escopo": feicoes_em_escopo,
                "feicoes_total": feicoes_total,
                "total_erros": total_erros,
                "erros": erros,
                "tempo_ms": tempo_ms,
                "carga_1min": carga_1min,
                "ram_livre_gb": ram_livre_gb,
                "medido_em": medido_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validacao_extensao_resultado_erros_item import (
            ValidacaoExtensaoResultadoErrosItem,  # noqa: PLC0415
        )

        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        versao_edicao = d.pop("versao_edicao")

        areas_processadas = d.pop("areas_processadas")

        areas_ativas_restantes = d.pop("areas_ativas_restantes")

        feicoes_em_escopo = d.pop("feicoes_em_escopo")

        feicoes_total = d.pop("feicoes_total")

        total_erros = d.pop("total_erros")

        erros = []
        _erros = d.pop("erros")
        for erros_item_data in _erros:
            erros_item = ValidacaoExtensaoResultadoErrosItem.from_dict(erros_item_data)

            erros.append(erros_item)

        tempo_ms = d.pop("tempo_ms")

        carga_1min = d.pop("carga_1min")

        ram_livre_gb = d.pop("ram_livre_gb")

        medido_em = d.pop("medido_em")

        validacao_extensao_resultado = cls(
            rede_id=rede_id,
            versao_edicao=versao_edicao,
            areas_processadas=areas_processadas,
            areas_ativas_restantes=areas_ativas_restantes,
            feicoes_em_escopo=feicoes_em_escopo,
            feicoes_total=feicoes_total,
            total_erros=total_erros,
            erros=erros,
            tempo_ms=tempo_ms,
            carga_1min=carga_1min,
            ram_livre_gb=ram_livre_gb,
            medido_em=medido_em,
        )

        validacao_extensao_resultado.additional_properties = d
        return validacao_extensao_resultado

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
