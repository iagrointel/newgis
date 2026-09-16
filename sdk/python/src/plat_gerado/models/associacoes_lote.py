from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.associacao_adicionar import AssociacaoAdicionar


T = TypeVar("T", bound="AssociacoesLote")


@_attrs_define
class AssociacoesLote:
    """
    Attributes:
        adicionar (list[AssociacaoAdicionar] | Unset):
        apagar (list[str] | Unset):
    """

    adicionar: list[AssociacaoAdicionar] | Unset = UNSET
    apagar: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        adicionar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.adicionar, Unset):
            adicionar = []
            for adicionar_item_data in self.adicionar:
                adicionar_item = adicionar_item_data.to_dict()
                adicionar.append(adicionar_item)

        apagar: list[str] | Unset = UNSET
        if not isinstance(self.apagar, Unset):
            apagar = self.apagar

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if adicionar is not UNSET:
            field_dict["adicionar"] = adicionar
        if apagar is not UNSET:
            field_dict["apagar"] = apagar

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.associacao_adicionar import AssociacaoAdicionar  # noqa: PLC0415

        d = dict(src_dict)
        _adicionar = d.pop("adicionar", UNSET)
        adicionar: list[AssociacaoAdicionar] | Unset = UNSET
        if _adicionar is not UNSET:
            adicionar = []
            for adicionar_item_data in _adicionar:
                adicionar_item = AssociacaoAdicionar.from_dict(adicionar_item_data)

                adicionar.append(adicionar_item)

        apagar = cast(list[str], d.pop("apagar", UNSET))

        associacoes_lote = cls(
            adicionar=adicionar,
            apagar=apagar,
        )

        return associacoes_lote
