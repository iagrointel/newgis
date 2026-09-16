from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApplyEditsResultado")


@_attrs_define
class ApplyEditsResultado:
    """
    Attributes:
        rede_id (str):
        regras_ativas (bool):
        adicionadas (list[str]):
        atualizadas (int):
        apagadas (int):
        associacoes_adicionadas (int):
        associacoes_apagadas (int):
        conexoes (int):
        area_sujas_criadas (int | Unset):  Default: 0.
    """

    rede_id: str
    regras_ativas: bool
    adicionadas: list[str]
    atualizadas: int
    apagadas: int
    associacoes_adicionadas: int
    associacoes_apagadas: int
    conexoes: int
    area_sujas_criadas: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        regras_ativas = self.regras_ativas

        adicionadas = self.adicionadas

        atualizadas = self.atualizadas

        apagadas = self.apagadas

        associacoes_adicionadas = self.associacoes_adicionadas

        associacoes_apagadas = self.associacoes_apagadas

        conexoes = self.conexoes

        area_sujas_criadas = self.area_sujas_criadas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "regras_ativas": regras_ativas,
                "adicionadas": adicionadas,
                "atualizadas": atualizadas,
                "apagadas": apagadas,
                "associacoes_adicionadas": associacoes_adicionadas,
                "associacoes_apagadas": associacoes_apagadas,
                "conexoes": conexoes,
            }
        )
        if area_sujas_criadas is not UNSET:
            field_dict["area_sujas_criadas"] = area_sujas_criadas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        regras_ativas = d.pop("regras_ativas")

        adicionadas = cast(list[str], d.pop("adicionadas"))

        atualizadas = d.pop("atualizadas")

        apagadas = d.pop("apagadas")

        associacoes_adicionadas = d.pop("associacoes_adicionadas")

        associacoes_apagadas = d.pop("associacoes_apagadas")

        conexoes = d.pop("conexoes")

        area_sujas_criadas = d.pop("area_sujas_criadas", UNSET)

        apply_edits_resultado = cls(
            rede_id=rede_id,
            regras_ativas=regras_ativas,
            adicionadas=adicionadas,
            atualizadas=atualizadas,
            apagadas=apagadas,
            associacoes_adicionadas=associacoes_adicionadas,
            associacoes_apagadas=associacoes_apagadas,
            conexoes=conexoes,
            area_sujas_criadas=area_sujas_criadas,
        )

        apply_edits_resultado.additional_properties = d
        return apply_edits_resultado

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
