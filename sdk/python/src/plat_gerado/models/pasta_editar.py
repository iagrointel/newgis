from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PastaEditar")


@_attrs_define
class PastaEditar:
    """
    Attributes:
        nome (None | str | Unset):
        pai_id (None | str | Unset):
        para_raiz (bool | Unset):  Default: False.
    """

    nome: None | str | Unset = UNSET
    pai_id: None | str | Unset = UNSET
    para_raiz: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        pai_id: None | str | Unset
        if isinstance(self.pai_id, Unset):
            pai_id = UNSET
        else:
            pai_id = self.pai_id

        para_raiz = self.para_raiz

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if pai_id is not UNSET:
            field_dict["pai_id"] = pai_id
        if para_raiz is not UNSET:
            field_dict["para_raiz"] = para_raiz

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_pai_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pai_id = _parse_pai_id(d.pop("pai_id", UNSET))

        para_raiz = d.pop("para_raiz", UNSET)

        pasta_editar = cls(
            nome=nome,
            pai_id=pai_id,
            para_raiz=para_raiz,
        )

        return pasta_editar
