from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LinkEntrada")


@_attrs_define
class LinkEntrada:
    """
    Attributes:
        nome (None | str | Unset):
        expira_em (None | str | Unset):
        itens_incluidos (list[str] | None | Unset):
        permite_download (bool | Unset):  Default: False.
    """

    nome: None | str | Unset = UNSET
    expira_em: None | str | Unset = UNSET
    itens_incluidos: list[str] | None | Unset = UNSET
    permite_download: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        expira_em: None | str | Unset
        if isinstance(self.expira_em, Unset):
            expira_em = UNSET
        else:
            expira_em = self.expira_em

        itens_incluidos: list[str] | None | Unset
        if isinstance(self.itens_incluidos, Unset):
            itens_incluidos = UNSET
        elif isinstance(self.itens_incluidos, list):
            itens_incluidos = self.itens_incluidos

        else:
            itens_incluidos = self.itens_incluidos

        permite_download = self.permite_download

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if nome is not UNSET:
            field_dict["nome"] = nome
        if expira_em is not UNSET:
            field_dict["expira_em"] = expira_em
        if itens_incluidos is not UNSET:
            field_dict["itens_incluidos"] = itens_incluidos
        if permite_download is not UNSET:
            field_dict["permite_download"] = permite_download

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

        def _parse_expira_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expira_em = _parse_expira_em(d.pop("expira_em", UNSET))

        def _parse_itens_incluidos(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                itens_incluidos_type_0 = cast(list[str], data)

                return itens_incluidos_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        itens_incluidos = _parse_itens_incluidos(d.pop("itens_incluidos", UNSET))

        permite_download = d.pop("permite_download", UNSET)

        link_entrada = cls(
            nome=nome,
            expira_em=expira_em,
            itens_incluidos=itens_incluidos,
            permite_download=permite_download,
        )

        return link_entrada
