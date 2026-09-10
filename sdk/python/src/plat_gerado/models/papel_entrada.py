from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PapelEntrada")


@_attrs_define
class PapelEntrada:
    """
    Attributes:
        nome (str):
        privilegios (list[str]):
        descricao (None | str | Unset):
    """

    nome: str
    privilegios: list[str]
    descricao: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        privilegios = self.privilegios

        descricao: None | str | Unset
        if isinstance(self.descricao, Unset):
            descricao = UNSET
        else:
            descricao = self.descricao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "privilegios": privilegios,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        privilegios = cast(list[str], d.pop("privilegios"))

        def _parse_descricao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        descricao = _parse_descricao(d.pop("descricao", UNSET))

        papel_entrada = cls(
            nome=nome,
            privilegios=privilegios,
            descricao=descricao,
        )

        return papel_entrada
