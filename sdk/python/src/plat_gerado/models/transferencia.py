from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.transferencia_novo_dono import TransferenciaNovoDono
    from ..models.transferencia_plano_item import TransferenciaPlanoItem


T = TypeVar("T", bound="Transferencia")


@_attrs_define
class Transferencia:
    """
    Attributes:
        plano (list[TransferenciaPlanoItem]):
        total (int):
        com_falha (int):
        novo_dono (TransferenciaNovoDono):
        executado (bool):
        transferidos (int):
    """

    plano: list[TransferenciaPlanoItem]
    total: int
    com_falha: int
    novo_dono: TransferenciaNovoDono
    executado: bool
    transferidos: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plano = []
        for plano_item_data in self.plano:
            plano_item = plano_item_data.to_dict()
            plano.append(plano_item)

        total = self.total

        com_falha = self.com_falha

        novo_dono = self.novo_dono.to_dict()

        executado = self.executado

        transferidos = self.transferidos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "plano": plano,
                "total": total,
                "com_falha": com_falha,
                "novo_dono": novo_dono,
                "executado": executado,
                "transferidos": transferidos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.transferencia_novo_dono import TransferenciaNovoDono  # noqa: PLC0415
        from ..models.transferencia_plano_item import TransferenciaPlanoItem  # noqa: PLC0415

        d = dict(src_dict)
        plano = []
        _plano = d.pop("plano")
        for plano_item_data in _plano:
            plano_item = TransferenciaPlanoItem.from_dict(plano_item_data)

            plano.append(plano_item)

        total = d.pop("total")

        com_falha = d.pop("com_falha")

        novo_dono = TransferenciaNovoDono.from_dict(d.pop("novo_dono"))

        executado = d.pop("executado")

        transferidos = d.pop("transferidos")

        transferencia = cls(
            plano=plano,
            total=total,
            com_falha=com_falha,
            novo_dono=novo_dono,
            executado=executado,
            transferidos=transferidos,
        )

        transferencia.additional_properties = d
        return transferencia

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
