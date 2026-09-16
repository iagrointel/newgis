from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ControladorEntrada")


@_attrs_define
class ControladorEntrada:
    """Marca o terminal de um dispositivo como controlador de uma subrede. `terminal` é obrigatório quando o
    tipo de ativo declara mais de um terminal no pacote. `nome` é o nome DO CONTROLADOR (único dentro do
    tier); sem ele, vale o nome da subrede.

        Attributes:
            feicao_id (str):
            subrede (str):
            tier (str):
            terminal (int | None | Unset):
            papel (str | Unset):  Default: 'fonte'.
            nome (None | str | Unset):
    """

    feicao_id: str
    subrede: str
    tier: str
    terminal: int | None | Unset = UNSET
    papel: str | Unset = "fonte"
    nome: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feicao_id = self.feicao_id

        subrede = self.subrede

        tier = self.tier

        terminal: int | None | Unset
        if isinstance(self.terminal, Unset):
            terminal = UNSET
        else:
            terminal = self.terminal

        papel = self.papel

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feicao_id": feicao_id,
                "subrede": subrede,
                "tier": tier,
            }
        )
        if terminal is not UNSET:
            field_dict["terminal"] = terminal
        if papel is not UNSET:
            field_dict["papel"] = papel
        if nome is not UNSET:
            field_dict["nome"] = nome

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        feicao_id = d.pop("feicao_id")

        subrede = d.pop("subrede")

        tier = d.pop("tier")

        def _parse_terminal(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        terminal = _parse_terminal(d.pop("terminal", UNSET))

        papel = d.pop("papel", UNSET)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        controlador_entrada = cls(
            feicao_id=feicao_id,
            subrede=subrede,
            tier=tier,
            terminal=terminal,
            papel=papel,
            nome=nome,
        )

        controlador_entrada.additional_properties = d
        return controlador_entrada

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
