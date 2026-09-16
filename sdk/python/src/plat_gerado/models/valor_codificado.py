from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ValorCodificado")


@_attrs_define
class ValorCodificado:
    """
    Attributes:
        codigo (str):
        descricao (str):
        ordem (int | None | Unset):
        ativo (bool | Unset):  Default: True.
    """

    codigo: str
    descricao: str
    ordem: int | None | Unset = UNSET
    ativo: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        descricao = self.descricao

        ordem: int | None | Unset
        if isinstance(self.ordem, Unset):
            ordem = UNSET
        else:
            ordem = self.ordem

        ativo = self.ativo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "codigo": codigo,
                "descricao": descricao,
            }
        )
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if ativo is not UNSET:
            field_dict["ativo"] = ativo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        codigo = d.pop("codigo")

        descricao = d.pop("descricao")

        def _parse_ordem(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ordem = _parse_ordem(d.pop("ordem", UNSET))

        ativo = d.pop("ativo", UNSET)

        valor_codificado = cls(
            codigo=codigo,
            descricao=descricao,
            ordem=ordem,
            ativo=ativo,
        )

        return valor_codificado
