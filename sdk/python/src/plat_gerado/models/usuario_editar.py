from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UsuarioEditar")


@_attrs_define
class UsuarioEditar:
    """
    Attributes:
        nome (None | str | Unset):
        email (None | str | Unset):
        perfil (None | str | Unset):
        papel_id (int | None | Unset):
        ativo (bool | None | Unset):
    """

    nome: None | str | Unset = UNSET
    email: None | str | Unset = UNSET
    perfil: None | str | Unset = UNSET
    papel_id: int | None | Unset = UNSET
    ativo: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        perfil: None | str | Unset
        if isinstance(self.perfil, Unset):
            perfil = UNSET
        else:
            perfil = self.perfil

        papel_id: int | None | Unset
        if isinstance(self.papel_id, Unset):
            papel_id = UNSET
        else:
            papel_id = self.papel_id

        ativo: bool | None | Unset
        if isinstance(self.ativo, Unset):
            ativo = UNSET
        else:
            ativo = self.ativo

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if email is not UNSET:
            field_dict["email"] = email
        if perfil is not UNSET:
            field_dict["perfil"] = perfil
        if papel_id is not UNSET:
            field_dict["papel_id"] = papel_id
        if ativo is not UNSET:
            field_dict["ativo"] = ativo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_perfil(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil = _parse_perfil(d.pop("perfil", UNSET))

        def _parse_papel_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        papel_id = _parse_papel_id(d.pop("papel_id", UNSET))

        def _parse_ativo(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        ativo = _parse_ativo(d.pop("ativo", UNSET))

        usuario_editar = cls(
            nome=nome,
            email=email,
            perfil=perfil,
            papel_id=papel_id,
            ativo=ativo,
        )

        return usuario_editar
