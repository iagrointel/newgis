from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AnotacaoEdicao")


@_attrs_define
class AnotacaoEdicao:
    """
    Attributes:
        texto (None | str | Unset):
        resolvido (bool | None | Unset):
    """

    texto: None | str | Unset = UNSET
    resolvido: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        texto: None | str | Unset
        if isinstance(self.texto, Unset):
            texto = UNSET
        else:
            texto = self.texto

        resolvido: bool | None | Unset
        if isinstance(self.resolvido, Unset):
            resolvido = UNSET
        else:
            resolvido = self.resolvido

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if texto is not UNSET:
            field_dict["texto"] = texto
        if resolvido is not UNSET:
            field_dict["resolvido"] = resolvido

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_texto(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        texto = _parse_texto(d.pop("texto", UNSET))

        def _parse_resolvido(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        resolvido = _parse_resolvido(d.pop("resolvido", UNSET))

        anotacao_edicao = cls(
            texto=texto,
            resolvido=resolvido,
        )

        anotacao_edicao.additional_properties = d
        return anotacao_edicao

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
