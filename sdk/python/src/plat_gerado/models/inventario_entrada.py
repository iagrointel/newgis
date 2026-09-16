from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="InventarioEntrada")


@_attrs_define
class InventarioEntrada:
    """
    Attributes:
        conexao_id (str):
        usuario (None | str | Unset):
        senha (None | str | Unset):
    """

    conexao_id: str
    usuario: None | str | Unset = UNSET
    senha: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        conexao_id = self.conexao_id

        usuario: None | str | Unset
        if isinstance(self.usuario, Unset):
            usuario = UNSET
        else:
            usuario = self.usuario

        senha: None | str | Unset
        if isinstance(self.senha, Unset):
            senha = UNSET
        else:
            senha = self.senha

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "conexao_id": conexao_id,
            }
        )
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if senha is not UNSET:
            field_dict["senha"] = senha

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conexao_id = d.pop("conexao_id")

        def _parse_usuario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario = _parse_usuario(d.pop("usuario", UNSET))

        def _parse_senha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        senha = _parse_senha(d.pop("senha", UNSET))

        inventario_entrada = cls(
            conexao_id=conexao_id,
            usuario=usuario,
            senha=senha,
        )

        return inventario_entrada
