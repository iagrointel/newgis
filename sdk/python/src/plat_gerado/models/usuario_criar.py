from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="UsuarioCriar")


@_attrs_define
class UsuarioCriar:
    """
    Attributes:
        login (str):
        nome (str):
        perfil (str):
        email (None | str | Unset):
        papel_id (int | None | Unset):
    """

    login: str
    nome: str
    perfil: str
    email: None | str | Unset = UNSET
    papel_id: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        login = self.login

        nome = self.nome

        perfil = self.perfil

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        papel_id: int | None | Unset
        if isinstance(self.papel_id, Unset):
            papel_id = UNSET
        else:
            papel_id = self.papel_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "login": login,
                "nome": nome,
                "perfil": perfil,
            }
        )
        if email is not UNSET:
            field_dict["email"] = email
        if papel_id is not UNSET:
            field_dict["papel_id"] = papel_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        login = d.pop("login")

        nome = d.pop("nome")

        perfil = d.pop("perfil")

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_papel_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        papel_id = _parse_papel_id(d.pop("papel_id", UNSET))

        usuario_criar = cls(
            login=login,
            nome=nome,
            perfil=perfil,
            email=email,
            papel_id=papel_id,
        )

        return usuario_criar
