from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="LigacaoEntradaRede")


@_attrs_define
class LigacaoEntradaRede:
    """
    Attributes:
        para_feicao_id (str):
    """

    para_feicao_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        para_feicao_id = self.para_feicao_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "para_feicao_id": para_feicao_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        para_feicao_id = d.pop("para_feicao_id")

        ligacao_entrada_rede = cls(
            para_feicao_id=para_feicao_id,
        )

        ligacao_entrada_rede.additional_properties = d
        return ligacao_entrada_rede

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
