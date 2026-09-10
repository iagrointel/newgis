from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.relacao_entrada import RelacaoEntrada


T = TypeVar("T", bound="RelacoesEntrada")


@_attrs_define
class RelacoesEntrada:
    """
    Attributes:
        relacoes (list[RelacaoEntrada]):
    """

    relacoes: list[RelacaoEntrada]

    def to_dict(self) -> dict[str, Any]:
        relacoes = []
        for relacoes_item_data in self.relacoes:
            relacoes_item = relacoes_item_data.to_dict()
            relacoes.append(relacoes_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "relacoes": relacoes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.relacao_entrada import RelacaoEntrada  # noqa: PLC0415

        d = dict(src_dict)
        relacoes = []
        _relacoes = d.pop("relacoes")
        for relacoes_item_data in _relacoes:
            relacoes_item = RelacaoEntrada.from_dict(relacoes_item_data)

            relacoes.append(relacoes_item)

        relacoes_entrada = cls(
            relacoes=relacoes,
        )

        return relacoes_entrada
