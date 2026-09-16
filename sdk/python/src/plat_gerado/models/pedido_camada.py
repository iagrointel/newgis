from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.objetivo import Objetivo


T = TypeVar("T", bound="PedidoCamada")


@_attrs_define
class PedidoCamada:
    """
    Attributes:
        execucao_id (str):
        objetivos (list[Objetivo]):
        ordens (int | Unset):  Default: 3.
        ordens_incluidas (list[int] | Unset): quais ordens entram na camada; [1] é só a fronteira
    """

    execucao_id: str
    objetivos: list[Objetivo]
    ordens: int | Unset = 3
    ordens_incluidas: list[int] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        execucao_id = self.execucao_id

        objetivos = []
        for objetivos_item_data in self.objetivos:
            objetivos_item = objetivos_item_data.to_dict()
            objetivos.append(objetivos_item)

        ordens = self.ordens

        ordens_incluidas: list[int] | Unset = UNSET
        if not isinstance(self.ordens_incluidas, Unset):
            ordens_incluidas = self.ordens_incluidas

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "execucao_id": execucao_id,
                "objetivos": objetivos,
            }
        )
        if ordens is not UNSET:
            field_dict["ordens"] = ordens
        if ordens_incluidas is not UNSET:
            field_dict["ordens_incluidas"] = ordens_incluidas

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

        ordens_incluidas = cast(list[int], d.pop("ordens_incluidas", UNSET))

        pedido_camada = cls(
            execucao_id=execucao_id,
            objetivos=objetivos,
            ordens=ordens,
            ordens_incluidas=ordens_incluidas,
        )

        return pedido_camada
