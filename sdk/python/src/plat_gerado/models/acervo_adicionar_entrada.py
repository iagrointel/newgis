from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AcervoAdicionarEntrada")


@_attrs_define
class AcervoAdicionarEntrada:
    """Corpo opcional de POST /api/acervo/{fonte_id}/adicionar (item L6-01-f-lgpd). Fonte marcada em
    `plat.acervo_lgpd.risco_pii` exige `confirma_risco_pii=true` explícito; sem isso a rota recusa com 409
    antes de criar qualquer item. Default false: nunca se confirma sozinho.

        Attributes:
            confirma_risco_pii (bool | Unset):  Default: False.
    """

    confirma_risco_pii: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        confirma_risco_pii = self.confirma_risco_pii

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if confirma_risco_pii is not UNSET:
            field_dict["confirma_risco_pii"] = confirma_risco_pii

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        confirma_risco_pii = d.pop("confirma_risco_pii", UNSET)

        acervo_adicionar_entrada = cls(
            confirma_risco_pii=confirma_risco_pii,
        )

        return acervo_adicionar_entrada
