from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RegioesEntrada")


@_attrs_define
class RegioesEntrada:
    """
    Attributes:
        n_regioes (int | Unset):  Default: 1.
        area_total_m2 (float | None | Unset):
        area_min_m2 (float | None | Unset):
        area_max_m2 (float | None | Unset):
        distancia_min_m (float | None | Unset):
        distancia_max_m (float | None | Unset):
        compromisso (int | Unset):  Default: 50.
        forma (str | Unset):  Default: 'circulo'.
        metodo (str | Unset):  Default: 'maior_media'.
        selecao (str | Unset):  Default: 'sequencial'.
        vizinhanca (int | Unset):  Default: 8.
        sem_ilhas (bool | Unset):  Default: True.
        sementes (str | Unset):  Default: 'auto'.
        resolucao_crescimento (str | Unset):  Default: 'auto'.
        semente_aleatoria (int | Unset):  Default: 0.
        so_aprovadas (bool | Unset): usar só as células aprovadas pela execução Default: False.
    """

    n_regioes: int | Unset = 1
    area_total_m2: float | None | Unset = UNSET
    area_min_m2: float | None | Unset = UNSET
    area_max_m2: float | None | Unset = UNSET
    distancia_min_m: float | None | Unset = UNSET
    distancia_max_m: float | None | Unset = UNSET
    compromisso: int | Unset = 50
    forma: str | Unset = "circulo"
    metodo: str | Unset = "maior_media"
    selecao: str | Unset = "sequencial"
    vizinhanca: int | Unset = 8
    sem_ilhas: bool | Unset = True
    sementes: str | Unset = "auto"
    resolucao_crescimento: str | Unset = "auto"
    semente_aleatoria: int | Unset = 0
    so_aprovadas: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        n_regioes = self.n_regioes

        area_total_m2: float | None | Unset
        if isinstance(self.area_total_m2, Unset):
            area_total_m2 = UNSET
        else:
            area_total_m2 = self.area_total_m2

        area_min_m2: float | None | Unset
        if isinstance(self.area_min_m2, Unset):
            area_min_m2 = UNSET
        else:
            area_min_m2 = self.area_min_m2

        area_max_m2: float | None | Unset
        if isinstance(self.area_max_m2, Unset):
            area_max_m2 = UNSET
        else:
            area_max_m2 = self.area_max_m2

        distancia_min_m: float | None | Unset
        if isinstance(self.distancia_min_m, Unset):
            distancia_min_m = UNSET
        else:
            distancia_min_m = self.distancia_min_m

        distancia_max_m: float | None | Unset
        if isinstance(self.distancia_max_m, Unset):
            distancia_max_m = UNSET
        else:
            distancia_max_m = self.distancia_max_m

        compromisso = self.compromisso

        forma = self.forma

        metodo = self.metodo

        selecao = self.selecao

        vizinhanca = self.vizinhanca

        sem_ilhas = self.sem_ilhas

        sementes = self.sementes

        resolucao_crescimento = self.resolucao_crescimento

        semente_aleatoria = self.semente_aleatoria

        so_aprovadas = self.so_aprovadas

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if n_regioes is not UNSET:
            field_dict["n_regioes"] = n_regioes
        if area_total_m2 is not UNSET:
            field_dict["area_total_m2"] = area_total_m2
        if area_min_m2 is not UNSET:
            field_dict["area_min_m2"] = area_min_m2
        if area_max_m2 is not UNSET:
            field_dict["area_max_m2"] = area_max_m2
        if distancia_min_m is not UNSET:
            field_dict["distancia_min_m"] = distancia_min_m
        if distancia_max_m is not UNSET:
            field_dict["distancia_max_m"] = distancia_max_m
        if compromisso is not UNSET:
            field_dict["compromisso"] = compromisso
        if forma is not UNSET:
            field_dict["forma"] = forma
        if metodo is not UNSET:
            field_dict["metodo"] = metodo
        if selecao is not UNSET:
            field_dict["selecao"] = selecao
        if vizinhanca is not UNSET:
            field_dict["vizinhanca"] = vizinhanca
        if sem_ilhas is not UNSET:
            field_dict["sem_ilhas"] = sem_ilhas
        if sementes is not UNSET:
            field_dict["sementes"] = sementes
        if resolucao_crescimento is not UNSET:
            field_dict["resolucao_crescimento"] = resolucao_crescimento
        if semente_aleatoria is not UNSET:
            field_dict["semente_aleatoria"] = semente_aleatoria
        if so_aprovadas is not UNSET:
            field_dict["so_aprovadas"] = so_aprovadas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        n_regioes = d.pop("n_regioes", UNSET)

        def _parse_area_total_m2(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        area_total_m2 = _parse_area_total_m2(d.pop("area_total_m2", UNSET))

        def _parse_area_min_m2(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        area_min_m2 = _parse_area_min_m2(d.pop("area_min_m2", UNSET))

        def _parse_area_max_m2(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        area_max_m2 = _parse_area_max_m2(d.pop("area_max_m2", UNSET))

        def _parse_distancia_min_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distancia_min_m = _parse_distancia_min_m(d.pop("distancia_min_m", UNSET))

        def _parse_distancia_max_m(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distancia_max_m = _parse_distancia_max_m(d.pop("distancia_max_m", UNSET))

        compromisso = d.pop("compromisso", UNSET)

        forma = d.pop("forma", UNSET)

        metodo = d.pop("metodo", UNSET)

        selecao = d.pop("selecao", UNSET)

        vizinhanca = d.pop("vizinhanca", UNSET)

        sem_ilhas = d.pop("sem_ilhas", UNSET)

        sementes = d.pop("sementes", UNSET)

        resolucao_crescimento = d.pop("resolucao_crescimento", UNSET)

        semente_aleatoria = d.pop("semente_aleatoria", UNSET)

        so_aprovadas = d.pop("so_aprovadas", UNSET)

        regioes_entrada = cls(
            n_regioes=n_regioes,
            area_total_m2=area_total_m2,
            area_min_m2=area_min_m2,
            area_max_m2=area_max_m2,
            distancia_min_m=distancia_min_m,
            distancia_max_m=distancia_max_m,
            compromisso=compromisso,
            forma=forma,
            metodo=metodo,
            selecao=selecao,
            vizinhanca=vizinhanca,
            sem_ilhas=sem_ilhas,
            sementes=sementes,
            resolucao_crescimento=resolucao_crescimento,
            semente_aleatoria=semente_aleatoria,
            so_aprovadas=so_aprovadas,
        )

        return regioes_entrada
