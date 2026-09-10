from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Resumo")


@_attrs_define
class Resumo:
    """
    Attributes:
        pendente (int):
        rodando (int):
        concluido_24h (int):
        falhou_24h (int):
        cancelado_24h (int):
    """

    pendente: int
    rodando: int
    concluido_24h: int
    falhou_24h: int
    cancelado_24h: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        pendente = self.pendente

        rodando = self.rodando

        concluido_24h = self.concluido_24h

        falhou_24h = self.falhou_24h

        cancelado_24h = self.cancelado_24h

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "pendente": pendente,
                "rodando": rodando,
                "concluido_24h": concluido_24h,
                "falhou_24h": falhou_24h,
                "cancelado_24h": cancelado_24h,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        pendente = d.pop("pendente")

        rodando = d.pop("rodando")

        concluido_24h = d.pop("concluido_24h")

        falhou_24h = d.pop("falhou_24h")

        cancelado_24h = d.pop("cancelado_24h")

        resumo = cls(
            pendente=pendente,
            rodando=rodando,
            concluido_24h=concluido_24h,
            falhou_24h=falhou_24h,
            cancelado_24h=cancelado_24h,
        )

        resumo.additional_properties = d
        return resumo

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
