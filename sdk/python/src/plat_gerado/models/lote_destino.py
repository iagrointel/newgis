from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.lote_destino_mapeamento import LoteDestinoMapeamento


T = TypeVar("T", bound="LoteDestino")


@_attrs_define
class LoteDestino:
    """
    Attributes:
        camada (str):
        mapeamento (LoteDestinoMapeamento | Unset):
    """

    camada: str
    mapeamento: LoteDestinoMapeamento | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        camada = self.camada

        mapeamento: dict[str, Any] | Unset = UNSET
        if not isinstance(self.mapeamento, Unset):
            mapeamento = self.mapeamento.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "camada": camada,
            }
        )
        if mapeamento is not UNSET:
            field_dict["mapeamento"] = mapeamento

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.lote_destino_mapeamento import LoteDestinoMapeamento  # noqa: PLC0415

        d = dict(src_dict)
        camada = d.pop("camada")

        _mapeamento = d.pop("mapeamento", UNSET)
        mapeamento: LoteDestinoMapeamento | Unset
        if isinstance(_mapeamento, Unset):
            mapeamento = UNSET
        else:
            mapeamento = LoteDestinoMapeamento.from_dict(_mapeamento)

        lote_destino = cls(
            camada=camada,
            mapeamento=mapeamento,
        )

        return lote_destino
