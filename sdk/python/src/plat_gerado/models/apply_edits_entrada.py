from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.associacoes_lote import AssociacoesLote
    from ..models.feicao_adicionar import FeicaoAdicionar
    from ..models.feicao_atualizar import FeicaoAtualizar


T = TypeVar("T", bound="ApplyEditsEntrada")


@_attrs_define
class ApplyEditsEntrada:
    """
    Attributes:
        adicionar (list[FeicaoAdicionar] | Unset):
        atualizar (list[FeicaoAtualizar] | Unset):
        apagar (list[str] | Unset):
        associacoes (AssociacoesLote | Unset):
    """

    adicionar: list[FeicaoAdicionar] | Unset = UNSET
    atualizar: list[FeicaoAtualizar] | Unset = UNSET
    apagar: list[str] | Unset = UNSET
    associacoes: AssociacoesLote | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        adicionar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.adicionar, Unset):
            adicionar = []
            for adicionar_item_data in self.adicionar:
                adicionar_item = adicionar_item_data.to_dict()
                adicionar.append(adicionar_item)

        atualizar: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.atualizar, Unset):
            atualizar = []
            for atualizar_item_data in self.atualizar:
                atualizar_item = atualizar_item_data.to_dict()
                atualizar.append(atualizar_item)

        apagar: list[str] | Unset = UNSET
        if not isinstance(self.apagar, Unset):
            apagar = self.apagar

        associacoes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.associacoes, Unset):
            associacoes = self.associacoes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if adicionar is not UNSET:
            field_dict["adicionar"] = adicionar
        if atualizar is not UNSET:
            field_dict["atualizar"] = atualizar
        if apagar is not UNSET:
            field_dict["apagar"] = apagar
        if associacoes is not UNSET:
            field_dict["associacoes"] = associacoes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.associacoes_lote import AssociacoesLote  # noqa: PLC0415
        from ..models.feicao_adicionar import FeicaoAdicionar  # noqa: PLC0415
        from ..models.feicao_atualizar import FeicaoAtualizar  # noqa: PLC0415

        d = dict(src_dict)
        _adicionar = d.pop("adicionar", UNSET)
        adicionar: list[FeicaoAdicionar] | Unset = UNSET
        if _adicionar is not UNSET:
            adicionar = []
            for adicionar_item_data in _adicionar:
                adicionar_item = FeicaoAdicionar.from_dict(adicionar_item_data)

                adicionar.append(adicionar_item)

        _atualizar = d.pop("atualizar", UNSET)
        atualizar: list[FeicaoAtualizar] | Unset = UNSET
        if _atualizar is not UNSET:
            atualizar = []
            for atualizar_item_data in _atualizar:
                atualizar_item = FeicaoAtualizar.from_dict(atualizar_item_data)

                atualizar.append(atualizar_item)

        apagar = cast(list[str], d.pop("apagar", UNSET))

        _associacoes = d.pop("associacoes", UNSET)
        associacoes: AssociacoesLote | Unset
        if isinstance(_associacoes, Unset):
            associacoes = UNSET
        else:
            associacoes = AssociacoesLote.from_dict(_associacoes)

        apply_edits_entrada = cls(
            adicionar=adicionar,
            atualizar=atualizar,
            apagar=apagar,
            associacoes=associacoes,
        )

        return apply_edits_entrada
