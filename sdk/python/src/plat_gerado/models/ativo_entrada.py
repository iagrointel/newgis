from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AtivoEntrada")


@_attrs_define
class AtivoEntrada:
    """
    Attributes:
        tipo_id (str):
        codigo_externo (None | str | Unset):
        numero (int | None | Unset):
    """

    tipo_id: str
    codigo_externo: None | str | Unset = UNSET
    numero: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_id = self.tipo_id

        codigo_externo: None | str | Unset
        if isinstance(self.codigo_externo, Unset):
            codigo_externo = UNSET
        else:
            codigo_externo = self.codigo_externo

        numero: int | None | Unset
        if isinstance(self.numero, Unset):
            numero = UNSET
        else:
            numero = self.numero

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo_id": tipo_id,
            }
        )
        if codigo_externo is not UNSET:
            field_dict["codigo_externo"] = codigo_externo
        if numero is not UNSET:
            field_dict["numero"] = numero

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo_id = d.pop("tipo_id")

        def _parse_codigo_externo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo_externo = _parse_codigo_externo(d.pop("codigo_externo", UNSET))

        def _parse_numero(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        numero = _parse_numero(d.pop("numero", UNSET))

        ativo_entrada = cls(
            tipo_id=tipo_id,
            codigo_externo=codigo_externo,
            numero=numero,
        )

        ativo_entrada.additional_properties = d
        return ativo_entrada

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
