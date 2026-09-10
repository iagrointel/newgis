from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConexaoTeste")


@_attrs_define
class ConexaoTeste:
    """
    Attributes:
        ok (bool):
        mensagem (str):
        latencia_ms (int):
        saude (str):
        saude_verificada_em (str):
        status (int | None | Unset):
    """

    ok: bool
    mensagem: str
    latencia_ms: int
    saude: str
    saude_verificada_em: str
    status: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ok = self.ok

        mensagem = self.mensagem

        latencia_ms = self.latencia_ms

        saude = self.saude

        saude_verificada_em = self.saude_verificada_em

        status: int | None | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        else:
            status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ok": ok,
                "mensagem": mensagem,
                "latencia_ms": latencia_ms,
                "saude": saude,
                "saude_verificada_em": saude_verificada_em,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ok = d.pop("ok")

        mensagem = d.pop("mensagem")

        latencia_ms = d.pop("latencia_ms")

        saude = d.pop("saude")

        saude_verificada_em = d.pop("saude_verificada_em")

        def _parse_status(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        conexao_teste = cls(
            ok=ok,
            mensagem=mensagem,
            latencia_ms=latencia_ms,
            saude=saude,
            saude_verificada_em=saude_verificada_em,
            status=status,
        )

        conexao_teste.additional_properties = d
        return conexao_teste

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
