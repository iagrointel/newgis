from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ModeloEntrada")


@_attrs_define
class ModeloEntrada:
    """
    Attributes:
        nome (str):
        descricao (str | Unset):  Default: ''.
        escopo (str | Unset):  Default: 'inquilino'.
        conteudo (None | str | Unset):
        item_id (None | str | Unset):
    """

    nome: str
    descricao: str | Unset = ""
    escopo: str | Unset = "inquilino"
    conteudo: None | str | Unset = UNSET
    item_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        descricao = self.descricao

        escopo = self.escopo

        conteudo: None | str | Unset
        if isinstance(self.conteudo, Unset):
            conteudo = UNSET
        else:
            conteudo = self.conteudo

        item_id: None | str | Unset
        if isinstance(self.item_id, Unset):
            item_id = UNSET
        else:
            item_id = self.item_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if escopo is not UNSET:
            field_dict["escopo"] = escopo
        if conteudo is not UNSET:
            field_dict["conteudo"] = conteudo
        if item_id is not UNSET:
            field_dict["item_id"] = item_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        descricao = d.pop("descricao", UNSET)

        escopo = d.pop("escopo", UNSET)

        def _parse_conteudo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        conteudo = _parse_conteudo(d.pop("conteudo", UNSET))

        def _parse_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_id = _parse_item_id(d.pop("item_id", UNSET))

        modelo_entrada = cls(
            nome=nome,
            descricao=descricao,
            escopo=escopo,
            conteudo=conteudo,
            item_id=item_id,
        )

        return modelo_entrada
