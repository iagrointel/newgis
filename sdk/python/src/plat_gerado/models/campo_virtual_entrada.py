from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CampoVirtualEntrada")


@_attrs_define
class CampoVirtualEntrada:
    """
    Attributes:
        nome (str):
        expressao (str):
        alias (None | str | Unset):
    """

    nome: str
    expressao: str
    alias: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        expressao = self.expressao

        alias: None | str | Unset
        if isinstance(self.alias, Unset):
            alias = UNSET
        else:
            alias = self.alias

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "expressao": expressao,
            }
        )
        if alias is not UNSET:
            field_dict["alias"] = alias

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        expressao = d.pop("expressao")

        def _parse_alias(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        alias = _parse_alias(d.pop("alias", UNSET))

        campo_virtual_entrada = cls(
            nome=nome,
            expressao=expressao,
            alias=alias,
        )

        return campo_virtual_entrada
