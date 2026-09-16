from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AgendaPedido")


@_attrs_define
class AgendaPedido:
    """
    Attributes:
        tipo (str):
        periodicidade (str):
        hora (int | Unset):  Default: 6.
        email (bool | Unset):  Default: True.
        fuso (str | Unset):  Default: 'America/Sao_Paulo'.
    """

    tipo: str
    periodicidade: str
    hora: int | Unset = 6
    email: bool | Unset = True
    fuso: str | Unset = "America/Sao_Paulo"

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        periodicidade = self.periodicidade

        hora = self.hora

        email = self.email

        fuso = self.fuso

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "periodicidade": periodicidade,
            }
        )
        if hora is not UNSET:
            field_dict["hora"] = hora
        if email is not UNSET:
            field_dict["email"] = email
        if fuso is not UNSET:
            field_dict["fuso"] = fuso

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo")

        periodicidade = d.pop("periodicidade")

        hora = d.pop("hora", UNSET)

        email = d.pop("email", UNSET)

        fuso = d.pop("fuso", UNSET)

        agenda_pedido = cls(
            tipo=tipo,
            periodicidade=periodicidade,
            hora=hora,
            email=email,
            fuso=fuso,
        )

        return agenda_pedido
