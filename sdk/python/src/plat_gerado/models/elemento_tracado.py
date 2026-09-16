from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ElementoTracado")


@_attrs_define
class ElementoTracado:
    """
    Attributes:
        feicao_id (str):
        tipo_id (None | str):
        grupo (None | str):
        tipo_chave (None | str):
        tipo_nome (None | str):
        terminal (int | None):
    """

    feicao_id: str
    tipo_id: None | str
    grupo: None | str
    tipo_chave: None | str
    tipo_nome: None | str
    terminal: int | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feicao_id = self.feicao_id

        tipo_id: None | str
        tipo_id = self.tipo_id

        grupo: None | str
        grupo = self.grupo

        tipo_chave: None | str
        tipo_chave = self.tipo_chave

        tipo_nome: None | str
        tipo_nome = self.tipo_nome

        terminal: int | None
        terminal = self.terminal

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feicao_id": feicao_id,
                "tipo_id": tipo_id,
                "grupo": grupo,
                "tipo_chave": tipo_chave,
                "tipo_nome": tipo_nome,
                "terminal": terminal,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        feicao_id = d.pop("feicao_id")

        def _parse_tipo_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_id = _parse_tipo_id(d.pop("tipo_id"))

        def _parse_grupo(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        grupo = _parse_grupo(d.pop("grupo"))

        def _parse_tipo_chave(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_chave = _parse_tipo_chave(d.pop("tipo_chave"))

        def _parse_tipo_nome(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        tipo_nome = _parse_tipo_nome(d.pop("tipo_nome"))

        def _parse_terminal(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        terminal = _parse_terminal(d.pop("terminal"))

        elemento_tracado = cls(
            feicao_id=feicao_id,
            tipo_id=tipo_id,
            grupo=grupo,
            tipo_chave=tipo_chave,
            tipo_nome=tipo_nome,
            terminal=terminal,
        )

        elemento_tracado.additional_properties = d
        return elemento_tracado

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
