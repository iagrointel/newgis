from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GradeSaida")


@_attrs_define
class GradeSaida:
    """
    Attributes:
        id (str):
        nivel (str):
        resolucao_m (float):
        colunas (int):
        linhas (int):
        celulas (int):
        celulas_possiveis (int):
        fator_aninhamento (int | None | Unset):
    """

    id: str
    nivel: str
    resolucao_m: float
    colunas: int
    linhas: int
    celulas: int
    celulas_possiveis: int
    fator_aninhamento: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nivel = self.nivel

        resolucao_m = self.resolucao_m

        colunas = self.colunas

        linhas = self.linhas

        celulas = self.celulas

        celulas_possiveis = self.celulas_possiveis

        fator_aninhamento: int | None | Unset
        if isinstance(self.fator_aninhamento, Unset):
            fator_aninhamento = UNSET
        else:
            fator_aninhamento = self.fator_aninhamento

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nivel": nivel,
                "resolucao_m": resolucao_m,
                "colunas": colunas,
                "linhas": linhas,
                "celulas": celulas,
                "celulas_possiveis": celulas_possiveis,
            }
        )
        if fator_aninhamento is not UNSET:
            field_dict["fator_aninhamento"] = fator_aninhamento

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        nivel = d.pop("nivel")

        resolucao_m = d.pop("resolucao_m")

        colunas = d.pop("colunas")

        linhas = d.pop("linhas")

        celulas = d.pop("celulas")

        celulas_possiveis = d.pop("celulas_possiveis")

        def _parse_fator_aninhamento(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        fator_aninhamento = _parse_fator_aninhamento(d.pop("fator_aninhamento", UNSET))

        grade_saida = cls(
            id=id,
            nivel=nivel,
            resolucao_m=resolucao_m,
            colunas=colunas,
            linhas=linhas,
            celulas=celulas,
            celulas_possiveis=celulas_possiveis,
            fator_aninhamento=fator_aninhamento,
        )

        grade_saida.additional_properties = d
        return grade_saida

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
