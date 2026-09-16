from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="TelemetriaEntrada")


@_attrs_define
class TelemetriaEntrada:
    """
    Attributes:
        ligada (bool):
        nome_instalacao (None | str | Unset):
    """

    ligada: bool
    nome_instalacao: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        ligada = self.ligada

        nome_instalacao: None | str | Unset
        if isinstance(self.nome_instalacao, Unset):
            nome_instalacao = UNSET
        else:
            nome_instalacao = self.nome_instalacao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ligada": ligada,
            }
        )
        if nome_instalacao is not UNSET:
            field_dict["nome_instalacao"] = nome_instalacao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ligada = d.pop("ligada")

        def _parse_nome_instalacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome_instalacao = _parse_nome_instalacao(d.pop("nome_instalacao", UNSET))

        telemetria_entrada = cls(
            ligada=ligada,
            nome_instalacao=nome_instalacao,
        )

        return telemetria_entrada
