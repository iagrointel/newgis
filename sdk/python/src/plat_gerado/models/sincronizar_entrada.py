from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.camada_mudancas import CamadaMudancas


T = TypeVar("T", bound="SincronizarEntrada")


@_attrs_define
class SincronizarEntrada:
    """
    Attributes:
        idempotencia (str):
        camadas (list[CamadaMudancas] | Unset):
        baixar (bool | Unset):  Default: True.
    """

    idempotencia: str
    camadas: list[CamadaMudancas] | Unset = UNSET
    baixar: bool | Unset = True

    def to_dict(self) -> dict[str, Any]:
        idempotencia = self.idempotencia

        camadas: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.camadas, Unset):
            camadas = []
            for camadas_item_data in self.camadas:
                camadas_item = camadas_item_data.to_dict()
                camadas.append(camadas_item)

        baixar = self.baixar

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "idempotencia": idempotencia,
            }
        )
        if camadas is not UNSET:
            field_dict["camadas"] = camadas
        if baixar is not UNSET:
            field_dict["baixar"] = baixar

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.camada_mudancas import CamadaMudancas  # noqa: PLC0415

        d = dict(src_dict)
        idempotencia = d.pop("idempotencia")

        _camadas = d.pop("camadas", UNSET)
        camadas: list[CamadaMudancas] | Unset = UNSET
        if _camadas is not UNSET:
            camadas = []
            for camadas_item_data in _camadas:
                camadas_item = CamadaMudancas.from_dict(camadas_item_data)

                camadas.append(camadas_item)

        baixar = d.pop("baixar", UNSET)

        sincronizar_entrada = cls(
            idempotencia=idempotencia,
            camadas=camadas,
            baixar=baixar,
        )

        return sincronizar_entrada
