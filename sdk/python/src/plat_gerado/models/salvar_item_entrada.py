from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SalvarItemEntrada")


@_attrs_define
class SalvarItemEntrada:
    """O que o usuário escolhe para o item do catálogo; o `dados` do item é montado pelo servidor.

    Attributes:
        titulo (str):
        resumo (None | str | Unset):
        tags (list[str] | Unset):
    """

    titulo: str
    resumo: None | str | Unset = UNSET
    tags: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        titulo = self.titulo

        resumo: None | str | Unset
        if isinstance(self.resumo, Unset):
            resumo = UNSET
        else:
            resumo = self.resumo

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "titulo": titulo,
            }
        )
        if resumo is not UNSET:
            field_dict["resumo"] = resumo
        if tags is not UNSET:
            field_dict["tags"] = tags

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        titulo = d.pop("titulo")

        def _parse_resumo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resumo = _parse_resumo(d.pop("resumo", UNSET))

        tags = cast(list[str], d.pop("tags", UNSET))

        salvar_item_entrada = cls(
            titulo=titulo,
            resumo=resumo,
            tags=tags,
        )

        return salvar_item_entrada
