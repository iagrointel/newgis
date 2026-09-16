from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.objetivo import Objetivo


T = TypeVar("T", bound="PedidoPareto")


@_attrs_define
class PedidoPareto:
    """
    Attributes:
        execucao_id (str):
        objetivos (list[Objetivo]):
        ordens (int | Unset):  Default: 3.
    """

    execucao_id: str
    objetivos: list[Objetivo]
    ordens: int | Unset = 3

    def to_dict(self) -> dict[str, Any]:
        execucao_id = self.execucao_id

        objetivos = []
        for objetivos_item_data in self.objetivos:
            objetivos_item = objetivos_item_data.to_dict()
            objetivos.append(objetivos_item)

        ordens = self.ordens

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "execucao_id": execucao_id,
                "objetivos": objetivos,
            }
        )
        if ordens is not UNSET:
            field_dict["ordens"] = ordens

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.objetivo import Objetivo  # noqa: PLC0415

        d = dict(src_dict)
        execucao_id = d.pop("execucao_id")

        objetivos = []
        _objetivos = d.pop("objetivos")
        for objetivos_item_data in _objetivos:
            objetivos_item = Objetivo.from_dict(objetivos_item_data)

            objetivos.append(objetivos_item)

        ordens = d.pop("ordens", UNSET)

        pedido_pareto = cls(
            execucao_id=execucao_id,
            objetivos=objetivos,
            ordens=ordens,
        )

        return pedido_pareto
