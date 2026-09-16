from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ArquivoUrlEntrada")


@_attrs_define
class ArquivoUrlEntrada:
    """Configuração da conexão como fonte de ARQUIVO por URL. `intervalo_s` só é usado quando `agendado`;
    os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05).

        Attributes:
            intervalo_s (int | Unset):  Default: 86400.
            agendado (bool | Unset):  Default: False.
    """

    intervalo_s: int | Unset = 86400
    agendado: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        intervalo_s = self.intervalo_s

        agendado = self.agendado

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if intervalo_s is not UNSET:
            field_dict["intervalo_s"] = intervalo_s
        if agendado is not UNSET:
            field_dict["agendado"] = agendado

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        intervalo_s = d.pop("intervalo_s", UNSET)

        agendado = d.pop("agendado", UNSET)

        arquivo_url_entrada = cls(
            intervalo_s=intervalo_s,
            agendado=agendado,
        )

        return arquivo_url_entrada
