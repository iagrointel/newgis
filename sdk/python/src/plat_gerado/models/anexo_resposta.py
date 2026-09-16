from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AnexoResposta")


@_attrs_define
class AnexoResposta:
    """
    Attributes:
        campo (str):
        nome (str):
        content_type (str):
        conteudo (str):
    """

    campo: str
    nome: str
    content_type: str
    conteudo: str

    def to_dict(self) -> dict[str, Any]:
        campo = self.campo

        nome = self.nome

        content_type = self.content_type

        conteudo = self.conteudo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "campo": campo,
                "nome": nome,
                "content_type": content_type,
                "conteudo": conteudo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        campo = d.pop("campo")

        nome = d.pop("nome")

        content_type = d.pop("content_type")

        conteudo = d.pop("conteudo")

        anexo_resposta = cls(
            campo=campo,
            nome=nome,
            content_type=content_type,
            conteudo=conteudo,
        )

        return anexo_resposta
