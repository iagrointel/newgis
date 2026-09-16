from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.execucao_entrada_amc_pesos_type_0 import ExecucaoEntradaAmcPesosType0


T = TypeVar("T", bound="ExecucaoEntradaAmc")


@_attrs_define
class ExecucaoEntradaAmc:
    """
    Attributes:
        modelo_id (str):
        conjunto_id (str):
        pesos (ExecucaoEntradaAmcPesosType0 | None | Unset): {fator_id: peso}; sem isto, os pesos do modelo
        semente (int | None | Unset):
    """

    modelo_id: str
    conjunto_id: str
    pesos: ExecucaoEntradaAmcPesosType0 | None | Unset = UNSET
    semente: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.execucao_entrada_amc_pesos_type_0 import ExecucaoEntradaAmcPesosType0  # noqa: PLC0415

        modelo_id = self.modelo_id

        conjunto_id = self.conjunto_id

        pesos: dict[str, Any] | None | Unset
        if isinstance(self.pesos, Unset):
            pesos = UNSET
        elif isinstance(self.pesos, ExecucaoEntradaAmcPesosType0):
            pesos = self.pesos.to_dict()
        else:
            pesos = self.pesos

        semente: int | None | Unset
        if isinstance(self.semente, Unset):
            semente = UNSET
        else:
            semente = self.semente

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "modelo_id": modelo_id,
                "conjunto_id": conjunto_id,
            }
        )
        if pesos is not UNSET:
            field_dict["pesos"] = pesos
        if semente is not UNSET:
            field_dict["semente"] = semente

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execucao_entrada_amc_pesos_type_0 import ExecucaoEntradaAmcPesosType0  # noqa: PLC0415

        d = dict(src_dict)
        modelo_id = d.pop("modelo_id")

        conjunto_id = d.pop("conjunto_id")

        def _parse_pesos(data: object) -> ExecucaoEntradaAmcPesosType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                pesos_type_0 = ExecucaoEntradaAmcPesosType0.from_dict(data)

                return pesos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ExecucaoEntradaAmcPesosType0 | None | Unset, data)

        pesos = _parse_pesos(d.pop("pesos", UNSET))

        def _parse_semente(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        semente = _parse_semente(d.pop("semente", UNSET))

        execucao_entrada_amc = cls(
            modelo_id=modelo_id,
            conjunto_id=conjunto_id,
            pesos=pesos,
            semente=semente,
        )

        execucao_entrada_amc.additional_properties = d
        return execucao_entrada_amc

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
