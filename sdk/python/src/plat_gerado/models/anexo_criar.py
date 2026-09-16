from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AnexoCriar")


@_attrs_define
class AnexoCriar:
    """
    Attributes:
        nome (str):
        tipo (str):
        conteudo (str):
    """

    nome: str
    tipo: str
    conteudo: str

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        tipo = self.tipo

        conteudo = self.conteudo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "tipo": tipo,
                "conteudo": conteudo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        tipo = d.pop("tipo")

        conteudo = d.pop("conteudo")

        anexo_criar = cls(
            nome=nome,
            tipo=tipo,
            conteudo=conteudo,
        )

        return anexo_criar
