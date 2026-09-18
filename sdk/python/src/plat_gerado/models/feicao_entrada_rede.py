from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FeicaoEntradaRede")


@_attrs_define
class FeicaoEntradaRede:
    """
    Attributes:
        tipo_id (str):
        codigo (str):
        controlador_ativo (bool | Unset):  Default: False.
    """

    tipo_id: str
    codigo: str
    controlador_ativo: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_id = self.tipo_id

        codigo = self.codigo

        controlador_ativo = self.controlador_ativo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo_id": tipo_id,
                "codigo": codigo,
            }
        )
        if controlador_ativo is not UNSET:
            field_dict["controlador_ativo"] = controlador_ativo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo_id = d.pop("tipo_id")

        codigo = d.pop("codigo")

        controlador_ativo = d.pop("controlador_ativo", UNSET)

        feicao_entrada_rede = cls(
            tipo_id=tipo_id,
            codigo=codigo,
            controlador_ativo=controlador_ativo,
        )

        feicao_entrada_rede.additional_properties = d
        return feicao_entrada_rede

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
