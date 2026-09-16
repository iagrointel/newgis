from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.subtipo_valor_padroes import SubtipoValorPadroes


T = TypeVar("T", bound="SubtipoValor")


@_attrs_define
class SubtipoValor:
    """
    Attributes:
        codigo (int):
        nome (str):
        padroes (SubtipoValorPadroes | Unset):
    """

    codigo: int
    nome: str
    padroes: SubtipoValorPadroes | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        nome = self.nome

        padroes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.padroes, Unset):
            padroes = self.padroes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "codigo": codigo,
                "nome": nome,
            }
        )
        if padroes is not UNSET:
            field_dict["padroes"] = padroes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subtipo_valor_padroes import SubtipoValorPadroes  # noqa: PLC0415

        d = dict(src_dict)
        codigo = d.pop("codigo")

        nome = d.pop("nome")

        _padroes = d.pop("padroes", UNSET)
        padroes: SubtipoValorPadroes | Unset
        if isinstance(_padroes, Unset):
            padroes = UNSET
        else:
            padroes = SubtipoValorPadroes.from_dict(_padroes)

        subtipo_valor = cls(
            codigo=codigo,
            nome=nome,
            padroes=padroes,
        )

        return subtipo_valor
