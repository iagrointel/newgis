from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ponto import Ponto


T = TypeVar("T", bound="CorredorEntrada")


@_attrs_define
class CorredorEntrada:
    """
    Attributes:
        origem (Ponto):
        destino (Ponto):
        custo_maximo (float | Unset): custo da pior nota (a melhor custa 1); a regra é linear e sai no manifesto
            Default: 10.0.
        sem_dado (str | Unset): célula sem nota: um de ('veto', 'custo_maximo') Default: 'veto'.
        veto_abaixo_de (float | None | Unset): nota abaixo da qual a célula é veto
        veto_nao_aprovadas (bool | Unset): célula não aprovada pela execução vira veto Default: False.
        vizinhanca (int | Unset): um de (4, 8, 16) Default: 16.
        epsilon (float | None | Unset): folga do corredor (0,05 = +5 %); nulo devolve só a linha Default: 0.05.
    """

    origem: Ponto
    destino: Ponto
    custo_maximo: float | Unset = 10.0
    sem_dado: str | Unset = "veto"
    veto_abaixo_de: float | None | Unset = UNSET
    veto_nao_aprovadas: bool | Unset = False
    vizinhanca: int | Unset = 16
    epsilon: float | None | Unset = 0.05

    def to_dict(self) -> dict[str, Any]:
        origem = self.origem.to_dict()

        destino = self.destino.to_dict()

        custo_maximo = self.custo_maximo

        sem_dado = self.sem_dado

        veto_abaixo_de: float | None | Unset
        if isinstance(self.veto_abaixo_de, Unset):
            veto_abaixo_de = UNSET
        else:
            veto_abaixo_de = self.veto_abaixo_de

        veto_nao_aprovadas = self.veto_nao_aprovadas

        vizinhanca = self.vizinhanca

        epsilon: float | None | Unset
        if isinstance(self.epsilon, Unset):
            epsilon = UNSET
        else:
            epsilon = self.epsilon

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "origem": origem,
                "destino": destino,
            }
        )
        if custo_maximo is not UNSET:
            field_dict["custo_maximo"] = custo_maximo
        if sem_dado is not UNSET:
            field_dict["sem_dado"] = sem_dado
        if veto_abaixo_de is not UNSET:
            field_dict["veto_abaixo_de"] = veto_abaixo_de
        if veto_nao_aprovadas is not UNSET:
            field_dict["veto_nao_aprovadas"] = veto_nao_aprovadas
        if vizinhanca is not UNSET:
            field_dict["vizinhanca"] = vizinhanca
        if epsilon is not UNSET:
            field_dict["epsilon"] = epsilon

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ponto import Ponto  # noqa: PLC0415

        d = dict(src_dict)
        origem = Ponto.from_dict(d.pop("origem"))

        destino = Ponto.from_dict(d.pop("destino"))

        custo_maximo = d.pop("custo_maximo", UNSET)

        sem_dado = d.pop("sem_dado", UNSET)

        def _parse_veto_abaixo_de(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        veto_abaixo_de = _parse_veto_abaixo_de(d.pop("veto_abaixo_de", UNSET))

        veto_nao_aprovadas = d.pop("veto_nao_aprovadas", UNSET)

        vizinhanca = d.pop("vizinhanca", UNSET)

        def _parse_epsilon(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        epsilon = _parse_epsilon(d.pop("epsilon", UNSET))

        corredor_entrada = cls(
            origem=origem,
            destino=destino,
            custo_maximo=custo_maximo,
            sem_dado=sem_dado,
            veto_abaixo_de=veto_abaixo_de,
            veto_nao_aprovadas=veto_nao_aprovadas,
            vizinhanca=vizinhanca,
            epsilon=epsilon,
        )

        return corredor_entrada
