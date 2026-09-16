from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.fator_entrada_papel import FatorEntradaPapel
from ..types import UNSET, Unset

T = TypeVar("T", bound="FatorEntrada")


@_attrs_define
class FatorEntrada:
    """
    Attributes:
        nome (str):
        resolucao_fonte_m (float): escala nativa DECLARADA da fonte, em metros
        papel (FatorEntradaPapel):
        unidade (str | Unset):  Default: ''.
        fonte (str | Unset):  Default: ''.
    """

    nome: str
    resolucao_fonte_m: float
    papel: FatorEntradaPapel
    unidade: str | Unset = ""
    fonte: str | Unset = ""

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        resolucao_fonte_m = self.resolucao_fonte_m

        papel = self.papel.value

        unidade = self.unidade

        fonte = self.fonte

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "resolucao_fonte_m": resolucao_fonte_m,
                "papel": papel,
            }
        )
        if unidade is not UNSET:
            field_dict["unidade"] = unidade
        if fonte is not UNSET:
            field_dict["fonte"] = fonte

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        nome = d.pop("nome")

        resolucao_fonte_m = d.pop("resolucao_fonte_m")

        papel = FatorEntradaPapel(d.pop("papel"))

        unidade = d.pop("unidade", UNSET)

        fonte = d.pop("fonte", UNSET)

        fator_entrada = cls(
            nome=nome,
            resolucao_fonte_m=resolucao_fonte_m,
            papel=papel,
            unidade=unidade,
            fonte=fonte,
        )

        return fator_entrada
