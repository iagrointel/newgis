from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AtivoConfigEntrada")


@_attrs_define
class AtivoConfigEntrada:
    """
    Attributes:
        cod_id (None | str | Unset):
        kva_nominal (float | None | Unset):
        tensao_nominal_v (float | None | Unset):
    """

    cod_id: None | str | Unset = UNSET
    kva_nominal: float | None | Unset = UNSET
    tensao_nominal_v: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        cod_id: None | str | Unset
        if isinstance(self.cod_id, Unset):
            cod_id = UNSET
        else:
            cod_id = self.cod_id

        kva_nominal: float | None | Unset
        if isinstance(self.kva_nominal, Unset):
            kva_nominal = UNSET
        else:
            kva_nominal = self.kva_nominal

        tensao_nominal_v: float | None | Unset
        if isinstance(self.tensao_nominal_v, Unset):
            tensao_nominal_v = UNSET
        else:
            tensao_nominal_v = self.tensao_nominal_v

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if cod_id is not UNSET:
            field_dict["cod_id"] = cod_id
        if kva_nominal is not UNSET:
            field_dict["kva_nominal"] = kva_nominal
        if tensao_nominal_v is not UNSET:
            field_dict["tensao_nominal_v"] = tensao_nominal_v

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_cod_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cod_id = _parse_cod_id(d.pop("cod_id", UNSET))

        def _parse_kva_nominal(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        kva_nominal = _parse_kva_nominal(d.pop("kva_nominal", UNSET))

        def _parse_tensao_nominal_v(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        tensao_nominal_v = _parse_tensao_nominal_v(d.pop("tensao_nominal_v", UNSET))

        ativo_config_entrada = cls(
            cod_id=cod_id,
            kva_nominal=kva_nominal,
            tensao_nominal_v=tensao_nominal_v,
        )

        return ativo_config_entrada
