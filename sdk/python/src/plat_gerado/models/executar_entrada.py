from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.executar_entrada_parametros import ExecutarEntradaParametros


T = TypeVar("T", bound="ExecutarEntrada")


@_attrs_define
class ExecutarEntrada:
    """
    Attributes:
        parametros (ExecutarEntradaParametros | Unset):
        timeout_s (int | Unset):  Default: 300.
    """

    parametros: ExecutarEntradaParametros | Unset = UNSET
    timeout_s: int | Unset = 300
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        parametros: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parametros, Unset):
            parametros = self.parametros.to_dict()

        timeout_s = self.timeout_s

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if parametros is not UNSET:
            field_dict["parametros"] = parametros
        if timeout_s is not UNSET:
            field_dict["timeout_s"] = timeout_s

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.executar_entrada_parametros import ExecutarEntradaParametros  # noqa: PLC0415

        d = dict(src_dict)
        _parametros = d.pop("parametros", UNSET)
        parametros: ExecutarEntradaParametros | Unset
        if isinstance(_parametros, Unset):
            parametros = UNSET
        else:
            parametros = ExecutarEntradaParametros.from_dict(_parametros)

        timeout_s = d.pop("timeout_s", UNSET)

        executar_entrada = cls(
            parametros=parametros,
            timeout_s=timeout_s,
        )

        executar_entrada.additional_properties = d
        return executar_entrada

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
