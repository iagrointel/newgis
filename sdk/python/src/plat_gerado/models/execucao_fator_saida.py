from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExecucaoFatorSaida")


@_attrs_define
class ExecucaoFatorSaida:
    """
    Attributes:
        fator_id (str):
        nome (str):
        peso (float):
        resolucao_fonte_m (float):
        resolucao_grade_m (float):
        razao_escala (float):
        escala (str):
        escala_grosseira (bool):
        blocos_usados (int):
        blocos_calculados (int):
        celulas_com_dado (int):
        valor_min (float | None | Unset):
        valor_max (float | None | Unset):
    """

    fator_id: str
    nome: str
    peso: float
    resolucao_fonte_m: float
    resolucao_grade_m: float
    razao_escala: float
    escala: str
    escala_grosseira: bool
    blocos_usados: int
    blocos_calculados: int
    celulas_com_dado: int
    valor_min: float | None | Unset = UNSET
    valor_max: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fator_id = self.fator_id

        nome = self.nome

        peso = self.peso

        resolucao_fonte_m = self.resolucao_fonte_m

        resolucao_grade_m = self.resolucao_grade_m

        razao_escala = self.razao_escala

        escala = self.escala

        escala_grosseira = self.escala_grosseira

        blocos_usados = self.blocos_usados

        blocos_calculados = self.blocos_calculados

        celulas_com_dado = self.celulas_com_dado

        valor_min: float | None | Unset
        if isinstance(self.valor_min, Unset):
            valor_min = UNSET
        else:
            valor_min = self.valor_min

        valor_max: float | None | Unset
        if isinstance(self.valor_max, Unset):
            valor_max = UNSET
        else:
            valor_max = self.valor_max

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fator_id": fator_id,
                "nome": nome,
                "peso": peso,
                "resolucao_fonte_m": resolucao_fonte_m,
                "resolucao_grade_m": resolucao_grade_m,
                "razao_escala": razao_escala,
                "escala": escala,
                "escala_grosseira": escala_grosseira,
                "blocos_usados": blocos_usados,
                "blocos_calculados": blocos_calculados,
                "celulas_com_dado": celulas_com_dado,
            }
        )
        if valor_min is not UNSET:
            field_dict["valor_min"] = valor_min
        if valor_max is not UNSET:
            field_dict["valor_max"] = valor_max

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fator_id = d.pop("fator_id")

        nome = d.pop("nome")

        peso = d.pop("peso")

        resolucao_fonte_m = d.pop("resolucao_fonte_m")

        resolucao_grade_m = d.pop("resolucao_grade_m")

        razao_escala = d.pop("razao_escala")

        escala = d.pop("escala")

        escala_grosseira = d.pop("escala_grosseira")

        blocos_usados = d.pop("blocos_usados")

        blocos_calculados = d.pop("blocos_calculados")

        celulas_com_dado = d.pop("celulas_com_dado")

        def _parse_valor_min(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        valor_min = _parse_valor_min(d.pop("valor_min", UNSET))

        def _parse_valor_max(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        valor_max = _parse_valor_max(d.pop("valor_max", UNSET))

        execucao_fator_saida = cls(
            fator_id=fator_id,
            nome=nome,
            peso=peso,
            resolucao_fonte_m=resolucao_fonte_m,
            resolucao_grade_m=resolucao_grade_m,
            razao_escala=razao_escala,
            escala=escala,
            escala_grosseira=escala_grosseira,
            blocos_usados=blocos_usados,
            blocos_calculados=blocos_calculados,
            celulas_com_dado=celulas_com_dado,
            valor_min=valor_min,
            valor_max=valor_max,
        )

        execucao_fator_saida.additional_properties = d
        return execucao_fator_saida

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
