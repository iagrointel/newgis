from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AnotacaoEntrada")


@_attrs_define
class AnotacaoEntrada:
    """
    Attributes:
        camada_id (str):
        fid (str):
        grupo_id (str):
        texto (str):
    """

    camada_id: str
    fid: str
    grupo_id: str
    texto: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        camada_id = self.camada_id

        fid = self.fid

        grupo_id = self.grupo_id

        texto = self.texto

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "camada_id": camada_id,
                "fid": fid,
                "grupo_id": grupo_id,
                "texto": texto,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        camada_id = d.pop("camada_id")

        fid = d.pop("fid")

        grupo_id = d.pop("grupo_id")

        texto = d.pop("texto")

        anotacao_entrada = cls(
            camada_id=camada_id,
            fid=fid,
            grupo_id=grupo_id,
            texto=texto,
        )

        anotacao_entrada.additional_properties = d
        return anotacao_entrada

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
