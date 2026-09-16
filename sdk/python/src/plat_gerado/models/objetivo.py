from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="Objetivo")


@_attrs_define
class Objetivo:
    """
    Attributes:
        fator_id (str): fator da execução (plat.escala_execucao_fator)
        direcao (str | Unset): maximizar ou minimizar Default: 'maximizar'.
        base (str | Unset): favorabilidade 0-100 transformada, ou valor bruto do fator Default: 'favorabilidade'.
    """

    fator_id: str
    direcao: str | Unset = "maximizar"
    base: str | Unset = "favorabilidade"

    def to_dict(self) -> dict[str, Any]:
        fator_id = self.fator_id

        direcao = self.direcao

        base = self.base

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "fator_id": fator_id,
            }
        )
        if direcao is not UNSET:
            field_dict["direcao"] = direcao
        if base is not UNSET:
            field_dict["base"] = base

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fator_id = d.pop("fator_id")

        direcao = d.pop("direcao", UNSET)

        base = d.pop("base", UNSET)

        objetivo = cls(
            fator_id=fator_id,
            direcao=direcao,
            base=base,
        )

        return objetivo
