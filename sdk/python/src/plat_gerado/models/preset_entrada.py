from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..models.preset_entrada_escopo import PresetEntradaEscopo
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preset_entrada_conteudo import PresetEntradaConteudo


T = TypeVar("T", bound="PresetEntrada")


@_attrs_define
class PresetEntrada:
    """
    Attributes:
        nome (str):
        conteudo (PresetEntradaConteudo): pesos e vetos por fator; ver app/amc/presets.py
        descricao (str | Unset):  Default: ''.
        escopo (PresetEntradaEscopo | Unset):  Default: PresetEntradaEscopo.USUARIO.
    """

    nome: str
    conteudo: PresetEntradaConteudo
    descricao: str | Unset = ""
    escopo: PresetEntradaEscopo | Unset = PresetEntradaEscopo.USUARIO

    def to_dict(self) -> dict[str, Any]:
        nome = self.nome

        conteudo = self.conteudo.to_dict()

        descricao = self.descricao

        escopo: str | Unset = UNSET
        if not isinstance(self.escopo, Unset):
            escopo = self.escopo.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "nome": nome,
                "conteudo": conteudo,
            }
        )
        if descricao is not UNSET:
            field_dict["descricao"] = descricao
        if escopo is not UNSET:
            field_dict["escopo"] = escopo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preset_entrada_conteudo import PresetEntradaConteudo  # noqa: PLC0415

        d = dict(src_dict)
        nome = d.pop("nome")

        conteudo = PresetEntradaConteudo.from_dict(d.pop("conteudo"))

        descricao = d.pop("descricao", UNSET)

        _escopo = d.pop("escopo", UNSET)
        escopo: PresetEntradaEscopo | Unset
        if isinstance(_escopo, Unset):
            escopo = UNSET
        else:
            escopo = PresetEntradaEscopo(_escopo)

        preset_entrada = cls(
            nome=nome,
            conteudo=conteudo,
            descricao=descricao,
            escopo=escopo,
        )

        return preset_entrada
