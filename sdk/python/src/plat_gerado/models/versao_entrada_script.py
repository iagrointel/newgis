from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VersaoEntradaScript")


@_attrs_define
class VersaoEntradaScript:
    """
    Attributes:
        codigo (str): texto completo da versão nova (o cabeçalho é revalidado)
        comentario (None | str | Unset):
    """

    codigo: str
    comentario: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        comentario: None | str | Unset
        if isinstance(self.comentario, Unset):
            comentario = UNSET
        else:
            comentario = self.comentario

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "codigo": codigo,
            }
        )
        if comentario is not UNSET:
            field_dict["comentario"] = comentario

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        codigo = d.pop("codigo")

        def _parse_comentario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        comentario = _parse_comentario(d.pop("comentario", UNSET))

        versao_entrada_script = cls(
            codigo=codigo,
            comentario=comentario,
        )

        versao_entrada_script.additional_properties = d
        return versao_entrada_script

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
