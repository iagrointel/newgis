from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TesteSaida")


@_attrs_define
class TesteSaida:
    """
    Attributes:
        ok (bool):
        mensagem (str):
        verificado_em (str):
        organizacao (None | str | Unset):
        usuario_agol (None | str | Unset):
        creditos_disponiveis (float | None | Unset):
    """

    ok: bool
    mensagem: str
    verificado_em: str
    organizacao: None | str | Unset = UNSET
    usuario_agol: None | str | Unset = UNSET
    creditos_disponiveis: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ok = self.ok

        mensagem = self.mensagem

        verificado_em = self.verificado_em

        organizacao: None | str | Unset
        if isinstance(self.organizacao, Unset):
            organizacao = UNSET
        else:
            organizacao = self.organizacao

        usuario_agol: None | str | Unset
        if isinstance(self.usuario_agol, Unset):
            usuario_agol = UNSET
        else:
            usuario_agol = self.usuario_agol

        creditos_disponiveis: float | None | Unset
        if isinstance(self.creditos_disponiveis, Unset):
            creditos_disponiveis = UNSET
        else:
            creditos_disponiveis = self.creditos_disponiveis

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ok": ok,
                "mensagem": mensagem,
                "verificado_em": verificado_em,
            }
        )
        if organizacao is not UNSET:
            field_dict["organizacao"] = organizacao
        if usuario_agol is not UNSET:
            field_dict["usuario_agol"] = usuario_agol
        if creditos_disponiveis is not UNSET:
            field_dict["creditos_disponiveis"] = creditos_disponiveis

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ok = d.pop("ok")

        mensagem = d.pop("mensagem")

        verificado_em = d.pop("verificado_em")

        def _parse_organizacao(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        organizacao = _parse_organizacao(d.pop("organizacao", UNSET))

        def _parse_usuario_agol(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario_agol = _parse_usuario_agol(d.pop("usuario_agol", UNSET))

        def _parse_creditos_disponiveis(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        creditos_disponiveis = _parse_creditos_disponiveis(d.pop("creditos_disponiveis", UNSET))

        teste_saida = cls(
            ok=ok,
            mensagem=mensagem,
            verificado_em=verificado_em,
            organizacao=organizacao,
            usuario_agol=usuario_agol,
            creditos_disponiveis=creditos_disponiveis,
        )

        teste_saida.additional_properties = d
        return teste_saida

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
