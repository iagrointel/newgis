from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.eu import Eu


T = TypeVar("T", bound="LoginSaida")


@_attrs_define
class LoginSaida:
    """
    Attributes:
        ok (bool):
        usuario (Eu | None | Unset):
        exige_2fa (bool | None | Unset):
        desafio (None | str | Unset):
        recuperacao_disponivel (bool | None | Unset):
    """

    ok: bool
    usuario: Eu | None | Unset = UNSET
    exige_2fa: bool | None | Unset = UNSET
    desafio: None | str | Unset = UNSET
    recuperacao_disponivel: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.eu import Eu  # noqa: PLC0415

        ok = self.ok

        usuario: dict[str, Any] | None | Unset
        if isinstance(self.usuario, Unset):
            usuario = UNSET
        elif isinstance(self.usuario, Eu):
            usuario = self.usuario.to_dict()
        else:
            usuario = self.usuario

        exige_2fa: bool | None | Unset
        if isinstance(self.exige_2fa, Unset):
            exige_2fa = UNSET
        else:
            exige_2fa = self.exige_2fa

        desafio: None | str | Unset
        if isinstance(self.desafio, Unset):
            desafio = UNSET
        else:
            desafio = self.desafio

        recuperacao_disponivel: bool | None | Unset
        if isinstance(self.recuperacao_disponivel, Unset):
            recuperacao_disponivel = UNSET
        else:
            recuperacao_disponivel = self.recuperacao_disponivel

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ok": ok,
            }
        )
        if usuario is not UNSET:
            field_dict["usuario"] = usuario
        if exige_2fa is not UNSET:
            field_dict["exige_2fa"] = exige_2fa
        if desafio is not UNSET:
            field_dict["desafio"] = desafio
        if recuperacao_disponivel is not UNSET:
            field_dict["recuperacao_disponivel"] = recuperacao_disponivel

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.eu import Eu  # noqa: PLC0415

        d = dict(src_dict)
        ok = d.pop("ok")

        def _parse_usuario(data: object) -> Eu | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                usuario_type_0 = Eu.from_dict(data)

                return usuario_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Eu | None | Unset, data)

        usuario = _parse_usuario(d.pop("usuario", UNSET))

        def _parse_exige_2fa(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        exige_2fa = _parse_exige_2fa(d.pop("exige_2fa", UNSET))

        def _parse_desafio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        desafio = _parse_desafio(d.pop("desafio", UNSET))

        def _parse_recuperacao_disponivel(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        recuperacao_disponivel = _parse_recuperacao_disponivel(d.pop("recuperacao_disponivel", UNSET))

        login_saida = cls(
            ok=ok,
            usuario=usuario,
            exige_2fa=exige_2fa,
            desafio=desafio,
            recuperacao_disponivel=recuperacao_disponivel,
        )

        login_saida.additional_properties = d
        return login_saida

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
