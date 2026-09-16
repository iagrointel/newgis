from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="RetencaoSaida")


@_attrs_define
class RetencaoSaida:
    """
    Attributes:
        retencao_dias (int):
        minimo_dias (int):
        maximo_dias (int):
        padrao_dias (int):
        job_expurgo (None | str):
    """

    retencao_dias: int
    minimo_dias: int
    maximo_dias: int
    padrao_dias: int
    job_expurgo: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        retencao_dias = self.retencao_dias

        minimo_dias = self.minimo_dias

        maximo_dias = self.maximo_dias

        padrao_dias = self.padrao_dias

        job_expurgo: None | str
        job_expurgo = self.job_expurgo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "retencao_dias": retencao_dias,
                "minimo_dias": minimo_dias,
                "maximo_dias": maximo_dias,
                "padrao_dias": padrao_dias,
                "job_expurgo": job_expurgo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        retencao_dias = d.pop("retencao_dias")

        minimo_dias = d.pop("minimo_dias")

        maximo_dias = d.pop("maximo_dias")

        padrao_dias = d.pop("padrao_dias")

        def _parse_job_expurgo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        job_expurgo = _parse_job_expurgo(d.pop("job_expurgo"))

        retencao_saida = cls(
            retencao_dias=retencao_dias,
            minimo_dias=minimo_dias,
            maximo_dias=maximo_dias,
            padrao_dias=padrao_dias,
            job_expurgo=job_expurgo,
        )

        retencao_saida.additional_properties = d
        return retencao_saida

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
