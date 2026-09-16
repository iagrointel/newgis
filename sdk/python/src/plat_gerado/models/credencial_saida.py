from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CredencialSaida")


@_attrs_define
class CredencialSaida:
    """
    Attributes:
        configurado (bool):
        portal (None | str | Unset):
        usuario (None | str | Unset):
        tipo (None | str | Unset):
        rotulo (None | str | Unset):
    """

    configurado: bool
    portal: None | str | Unset = UNSET
    usuario: None | str | Unset = UNSET
    tipo: None | str | Unset = UNSET
    rotulo: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        configurado = self.configurado

        portal: None | str | Unset
        if isinstance(self.portal, Unset):
            portal = UNSET
        else:
            portal = self.portal

        usuario: None | str | Unset
        if isinstance(self.usuario, Unset):
            usuario = UNSET
        else:
            usuario = self.usuario

        tipo: None | str | Unset
        if isinstance(self.tipo, Unset):
            tipo = UNSET
        else:
            tipo = self.tipo

        rotulo: None | str | Unset
        if isinstance(self.rotulo, Unset):
            rotulo = UNSET
        else:
            rotulo = self.rotulo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "configurado": configurado,
            }
        )
        if portal is not UNSET:
            field_dict["portal"] = portal
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if tipo is not UNSET:
            field_dict["tipo"] = tipo
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        configurado = d.pop("configurado")

        def _parse_portal(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        portal = _parse_portal(d.pop("portal", UNSET))

        def _parse_usuario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        usuario = _parse_usuario(d.pop("usuario", UNSET))

        def _parse_tipo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tipo = _parse_tipo(d.pop("tipo", UNSET))

        def _parse_rotulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rotulo = _parse_rotulo(d.pop("rotulo", UNSET))

        credencial_saida = cls(
            configurado=configurado,
            portal=portal,
            usuario=usuario,
            tipo=tipo,
            rotulo=rotulo,
        )

        credencial_saida.additional_properties = d
        return credencial_saida

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
