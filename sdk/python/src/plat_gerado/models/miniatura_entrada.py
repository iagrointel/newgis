from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MiniaturaEntrada")


@_attrs_define
class MiniaturaEntrada:
    """Imagem em base64 (JSON: o CSRF sob cookie exige application/json; multipart entra com o L0-11).

    Attributes:
        conteudo (str):
        nome (None | str | Unset):
    """

    conteudo: str
    nome: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        conteudo = self.conteudo

        nome: None | str | Unset
        if isinstance(self.nome, Unset):
            nome = UNSET
        else:
            nome = self.nome

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "conteudo": conteudo,
            }
        )
        if nome is not UNSET:
            field_dict["nome"] = nome

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conteudo = d.pop("conteudo")

        def _parse_nome(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        nome = _parse_nome(d.pop("nome", UNSET))

        miniatura_entrada = cls(
            conteudo=conteudo,
            nome=nome,
        )

        return miniatura_entrada
