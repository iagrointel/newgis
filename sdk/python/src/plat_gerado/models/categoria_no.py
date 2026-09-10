from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CategoriaNo")


@_attrs_define
class CategoriaNo:
    """
    Attributes:
        nome (str):
        id (None | str | Unset):
        codigo (None | str | Unset):
        filhas (list[CategoriaNo] | Unset):
    """

    nome: str
    id: None | str | Unset = UNSET
    codigo: None | str | Unset = UNSET
    filhas: list[CategoriaNo] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        codigo: None | str | Unset
        if isinstance(self.codigo, Unset):
            codigo = UNSET
        else:
            codigo = self.codigo

        filhas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.filhas, Unset):
            filhas = []
            for filhas_item_data in self.filhas:
                filhas_item = filhas_item_data.to_dict()
                filhas.append(filhas_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if codigo is not UNSET:
            field_dict["codigo"] = codigo
        if filhas is not UNSET:
            field_dict["filhas"] = filhas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_codigo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        codigo = _parse_codigo(d.pop("codigo", UNSET))

        _filhas = d.pop("filhas", UNSET)
        filhas: list[CategoriaNo] | Unset = UNSET
        if _filhas is not UNSET:
            filhas = []
            for filhas_item_data in _filhas:
                filhas_item = CategoriaNo.from_dict(filhas_item_data)

                filhas.append(filhas_item)

        categoria_no = cls(
            nome=nome,
            id=id,
            codigo=codigo,
            filhas=filhas,
        )

        return categoria_no
