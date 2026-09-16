from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TopologiaResumo")


@_attrs_define
class TopologiaResumo:
    """
    Attributes:
        rede_id (str):
        tolerancia_m (float):
        nos (int):
        arestas (int):
        nos_orfaos (int):
        arestas_sem_no (int):
        duracao_ms (int):
        construido_em (str):
    """

    rede_id: str
    tolerancia_m: float
    nos: int
    arestas: int
    nos_orfaos: int
    arestas_sem_no: int
    duracao_ms: int
    construido_em: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        tolerancia_m = self.tolerancia_m

        nos = self.nos

        arestas = self.arestas

        nos_orfaos = self.nos_orfaos

        arestas_sem_no = self.arestas_sem_no

        duracao_ms = self.duracao_ms

        construido_em = self.construido_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "tolerancia_m": tolerancia_m,
                "nos": nos,
                "arestas": arestas,
                "nos_orfaos": nos_orfaos,
                "arestas_sem_no": arestas_sem_no,
                "duracao_ms": duracao_ms,
                "construido_em": construido_em,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        tolerancia_m = d.pop("tolerancia_m")

        nos = d.pop("nos")

        arestas = d.pop("arestas")

        nos_orfaos = d.pop("nos_orfaos")

        arestas_sem_no = d.pop("arestas_sem_no")

        duracao_ms = d.pop("duracao_ms")

        construido_em = d.pop("construido_em")

        topologia_resumo = cls(
            rede_id=rede_id,
            tolerancia_m=tolerancia_m,
            nos=nos,
            arestas=arestas,
            nos_orfaos=nos_orfaos,
            arestas_sem_no=arestas_sem_no,
            duracao_ms=duracao_ms,
            construido_em=construido_em,
        )

        topologia_resumo.additional_properties = d
        return topologia_resumo

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
