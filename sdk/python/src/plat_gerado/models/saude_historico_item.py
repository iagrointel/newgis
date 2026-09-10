from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SaudeHistoricoItem")


@_attrs_define
class SaudeHistoricoItem:
    """
    Attributes:
        verificada_em (str):
        ok (bool):
        status (int | None | Unset):
        mensagem (None | str | Unset):
        latencia_ms (int | None | Unset):
    """

    verificada_em: str
    ok: bool
    status: int | None | Unset = UNSET
    mensagem: None | str | Unset = UNSET
    latencia_ms: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        verificada_em = self.verificada_em

        ok = self.ok

        status: int | None | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        mensagem: None | str | Unset
        if isinstance(self.mensagem, Unset):
            mensagem = UNSET
        else:
            mensagem = self.mensagem

        latencia_ms: int | None | Unset
        if isinstance(self.latencia_ms, Unset):
            latencia_ms = UNSET
        else:
            latencia_ms = self.latencia_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "verificada_em": verificada_em,
                "ok": ok,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status
        if mensagem is not UNSET:
            field_dict["mensagem"] = mensagem
        if latencia_ms is not UNSET:
            field_dict["latencia_ms"] = latencia_ms

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        verificada_em = d.pop("verificada_em")

        ok = d.pop("ok")

        def _parse_status(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        def _parse_mensagem(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mensagem = _parse_mensagem(d.pop("mensagem", UNSET))

        def _parse_latencia_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        latencia_ms = _parse_latencia_ms(d.pop("latencia_ms", UNSET))

        saude_historico_item = cls(
            verificada_em=verificada_em,
            ok=ok,
            status=status,
            mensagem=mensagem,
            latencia_ms=latencia_ms,
        )

        saude_historico_item.additional_properties = d
        return saude_historico_item

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
