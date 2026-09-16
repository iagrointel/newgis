from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.qualidade_entrada_tipo_type_0 import QualidadeEntradaTipoType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="QualidadeEntrada")


@_attrs_define
class QualidadeEntrada:
    """
    Attributes:
        tipo (None | QualidadeEntradaTipoType0 | Unset):
        tolerancia_m2 (float | Unset):  Default: 0.01.
    """

    tipo: None | QualidadeEntradaTipoType0 | Unset = UNSET
    tolerancia_m2: float | Unset = 0.01
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo: None | str | Unset
        if isinstance(self.tipo, Unset):
            tipo = UNSET
        elif isinstance(self.tipo, QualidadeEntradaTipoType0):
            tipo = self.tipo.value
        else:
            tipo = self.tipo

        tolerancia_m2 = self.tolerancia_m2

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if tolerancia_m2 is not UNSET:
            field_dict["toleranciaM2"] = tolerancia_m2

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_tipo(data: object) -> None | QualidadeEntradaTipoType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tipo_type_0 = QualidadeEntradaTipoType0(data)

                return tipo_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | QualidadeEntradaTipoType0 | Unset, data)

        tipo = _parse_tipo(d.pop("tipo", UNSET))

        tolerancia_m2 = d.pop("toleranciaM2", UNSET)

        qualidade_entrada = cls(
            tipo=tipo,
            tolerancia_m2=tolerancia_m2,
        )

        qualidade_entrada.additional_properties = d
        return qualidade_entrada

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
