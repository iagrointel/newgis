from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="LinhaLog")


@_attrs_define
class LinhaLog:
    """
    Attributes:
        id (int):
        em (str):
        nivel (str):
        mensagem (str):
    """

    id: int
    em: str
    nivel: str
    mensagem: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        em = self.em

        nivel = self.nivel

        mensagem = self.mensagem

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "em": em,
                "nivel": nivel,
                "mensagem": mensagem,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        em = d.pop("em")

        nivel = d.pop("nivel")

        mensagem = d.pop("mensagem")

        linha_log = cls(
            id=id,
            em=em,
            nivel=nivel,
            mensagem=mensagem,
        )

        linha_log.additional_properties = d
        return linha_log

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
