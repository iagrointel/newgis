from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SMTPSaida")


@_attrs_define
class SMTPSaida:
    """
    Attributes:
        configurado (bool):
        origem (str):
        host (None | str | Unset):
        porta (int | None | Unset):
        tls (bool | None | Unset):
        usuario (None | str | Unset):
        remetente (None | str | Unset):
        rotulo (None | str | Unset):
        senha_configurada (bool | Unset):  Default: False.
    """

    configurado: bool
    origem: str
    host: None | str | Unset = UNSET
    porta: int | None | Unset = UNSET
    tls: bool | None | Unset = UNSET
    usuario: None | str | Unset = UNSET
    remetente: None | str | Unset = UNSET
    rotulo: None | str | Unset = UNSET
    senha_configurada: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        configurado = self.configurado

        origem = self.origem

        host: None | str | Unset
        if isinstance(self.host, Unset):
            host = UNSET
        else:
            host = self.host

        porta: int | None | Unset
        if isinstance(self.porta, Unset):
            porta = UNSET
        else:
            porta = self.porta

        tls: bool | None | Unset
        if isinstance(self.tls, Unset):
            tls = UNSET
        else:
            tls = self.tls

        usuario: None | str | Unset
        if isinstance(self.usuario, Unset):
            usuario = UNSET
        else:
            usuario = self.usuario

        remetente: None | str | Unset
        if isinstance(self.remetente, Unset):
            remetente = UNSET
        else:
            remetente = self.remetente

        rotulo: None | str | Unset
        if isinstance(self.rotulo, Unset):
            rotulo = UNSET
        else:
            rotulo = self.rotulo

        senha_configurada = self.senha_configurada

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "configurado": configurado,
                "origem": origem,
            }
        )
        if host is not UNSET:
            field_dict["host"] = host
        if porta is not UNSET:
            field_dict["porta"] = porta
        if tls is not UNSET:
            field_dict["tls"] = tls
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if remetente is not UNSET:
            field_dict["remetente"] = remetente
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo
        if senha_configurada is not UNSET:
            field_dict["senha_configurada"] = senha_configurada

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        configurado = d.pop("configurado")

        origem = d.pop("origem")

        def _parse_host(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        host = _parse_host(d.pop("host", UNSET))

        def _parse_porta(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        porta = _parse_porta(d.pop("porta", UNSET))

        def _parse_tls(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        tls = _parse_tls(d.pop("tls", UNSET))

        def _parse_usuario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario = _parse_usuario(d.pop("usuario", UNSET))

        def _parse_remetente(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        remetente = _parse_remetente(d.pop("remetente", UNSET))

        def _parse_rotulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rotulo = _parse_rotulo(d.pop("rotulo", UNSET))

        senha_configurada = d.pop("senha_configurada", UNSET)

        smtp_saida = cls(
            configurado=configurado,
            origem=origem,
            host=host,
            porta=porta,
            tls=tls,
            usuario=usuario,
            remetente=remetente,
            rotulo=rotulo,
            senha_configurada=senha_configurada,
        )

        smtp_saida.additional_properties = d
        return smtp_saida

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
