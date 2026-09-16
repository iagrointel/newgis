from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PublicacaoEntrada")


@_attrs_define
class PublicacaoEntrada:
    """
    Attributes:
        slug (str):
        dominios_permitidos (list[str] | None | Unset):
        versao (int | None | Unset):
    """

    slug: str
    dominios_permitidos: list[str] | None | Unset = UNSET
    versao: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        slug = self.slug

        dominios_permitidos: list[str] | None | Unset
        if isinstance(self.dominios_permitidos, Unset):
            dominios_permitidos = UNSET
        elif isinstance(self.dominios_permitidos, list):
            dominios_permitidos = self.dominios_permitidos

        else:
            dominios_permitidos = self.dominios_permitidos

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "slug": slug,
            }
        )
        if dominios_permitidos is not UNSET:
            field_dict["dominios_permitidos"] = dominios_permitidos
        if versao is not UNSET:
            field_dict["versao"] = versao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        slug = d.pop("slug")

        def _parse_dominios_permitidos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                dominios_permitidos_type_0 = cast(list[str], data)

                return dominios_permitidos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        dominios_permitidos = _parse_dominios_permitidos(d.pop("dominios_permitidos", UNSET))

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        publicacao_entrada = cls(
            slug=slug,
            dominios_permitidos=dominios_permitidos,
            versao=versao,
        )

        return publicacao_entrada
