from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ConviteMembroEntrada")


@_attrs_define
class ConviteMembroEntrada:
    """
    Attributes:
        email (str):
        perfil (str):
        nome_sugerido (None | str | Unset):
        papel_id (int | None | Unset):
    """

    email: str
    perfil: str
    nome_sugerido: None | str | Unset = UNSET
    papel_id: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        perfil = self.perfil

        nome_sugerido: None | str | Unset
        if isinstance(self.nome_sugerido, Unset):
            nome_sugerido = UNSET
        else:
            nome_sugerido = self.nome_sugerido

        papel_id: int | None | Unset
        if isinstance(self.papel_id, Unset):
            papel_id = UNSET
        else:
            papel_id = self.papel_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
                "perfil": perfil,
            }
        )
        if nome_sugerido is not UNSET:
            field_dict["nome_sugerido"] = nome_sugerido
        if papel_id is not UNSET:
            field_dict["papel_id"] = papel_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        perfil = d.pop("perfil")

        def _parse_nome_sugerido(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome_sugerido = _parse_nome_sugerido(d.pop("nome_sugerido", UNSET))

        def _parse_papel_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        papel_id = _parse_papel_id(d.pop("papel_id", UNSET))

        convite_membro_entrada = cls(
            email=email,
            perfil=perfil,
            nome_sugerido=nome_sugerido,
            papel_id=papel_id,
        )

        return convite_membro_entrada
