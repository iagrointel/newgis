from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="Login2FAEntrada")


@_attrs_define
class Login2FAEntrada:
    """
    Attributes:
        desafio (str):
        codigo (None | str | Unset):
        codigo_recuperacao (None | str | Unset):
    """

    desafio: str
    codigo: None | str | Unset = UNSET
    codigo_recuperacao: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        desafio = self.desafio

        codigo: None | str | Unset
        if isinstance(self.codigo, Unset):
            codigo = UNSET
        else:
            codigo = self.codigo

        codigo_recuperacao: None | str | Unset
        if isinstance(self.codigo_recuperacao, Unset):
            codigo_recuperacao = UNSET
        else:
            codigo_recuperacao = self.codigo_recuperacao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "desafio": desafio,
            }
        )
        if codigo is not UNSET:
            field_dict["codigo"] = codigo
        if codigo_recuperacao is not UNSET:
            field_dict["codigo_recuperacao"] = codigo_recuperacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        desafio = d.pop("desafio")

        def _parse_codigo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo = _parse_codigo(d.pop("codigo", UNSET))

        def _parse_codigo_recuperacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo_recuperacao = _parse_codigo_recuperacao(d.pop("codigo_recuperacao", UNSET))

        login_2fa_entrada = cls(
            desafio=desafio,
            codigo=codigo,
            codigo_recuperacao=codigo_recuperacao,
        )

        return login_2fa_entrada
