from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Sessao")


@_attrs_define
class Sessao:
    """
    Attributes:
        id (str):
        criado_em (None | str):
        ultimo_uso (None | str):
        expira_em (None | str):
        ip (None | str):
        agente (None | str):
        atual (bool):
    """

    id: str
    criado_em: None | str
    ultimo_uso: None | str
    expira_em: None | str
    ip: None | str
    agente: None | str
    atual: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        criado_em: None | str
        criado_em = self.criado_em

        ultimo_uso: None | str
        ultimo_uso = self.ultimo_uso

        expira_em: None | str
        expira_em = self.expira_em

        ip: None | str
        ip = self.ip

        agente: None | str
        agente = self.agente

        atual = self.atual

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "criado_em": criado_em,
                "ultimo_uso": ultimo_uso,
                "expira_em": expira_em,
                "ip": ip,
                "agente": agente,
                "atual": atual,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        def _parse_criado_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        criado_em = _parse_criado_em(d.pop("criado_em"))

        def _parse_ultimo_uso(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ultimo_uso = _parse_ultimo_uso(d.pop("ultimo_uso"))

        def _parse_expira_em(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        expira_em = _parse_expira_em(d.pop("expira_em"))

        def _parse_ip(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ip = _parse_ip(d.pop("ip"))

        def _parse_agente(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        agente = _parse_agente(d.pop("agente"))

        atual = d.pop("atual")

        sessao = cls(
            id=id,
            criado_em=criado_em,
            ultimo_uso=ultimo_uso,
            expira_em=expira_em,
            ip=ip,
            agente=agente,
            atual=atual,
        )

        sessao.additional_properties = d
        return sessao

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
