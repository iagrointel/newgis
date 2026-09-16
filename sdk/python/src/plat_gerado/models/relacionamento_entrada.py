from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RelacionamentoEntrada")


@_attrs_define
class RelacionamentoEntrada:
    """
    Attributes:
        origem_item_id (str):
        destino_item_id (str):
        cardinalidade (str):
        nome_direto (str):
        nome_inverso (str):
        chave_origem (str | Unset):  Default: 'globalid'.
        chave_destino (str | Unset):  Default: 'globalid'.
        composto (bool | Unset):  Default: False.
        cardinalidade_min (int | None | Unset):
        cardinalidade_max (int | None | Unset):
        limite_relacionados (int | Unset):  Default: 2000.
    """

    origem_item_id: str
    destino_item_id: str
    cardinalidade: str
    nome_direto: str
    nome_inverso: str
    chave_origem: str | Unset = "globalid"
    chave_destino: str | Unset = "globalid"
    composto: bool | Unset = False
    cardinalidade_min: int | None | Unset = UNSET
    cardinalidade_max: int | None | Unset = UNSET
    limite_relacionados: int | Unset = 2000

    def to_dict(self) -> dict[str, Any]:
        origem_item_id = self.origem_item_id

        destino_item_id = self.destino_item_id

        cardinalidade = self.cardinalidade

        nome_direto = self.nome_direto

        nome_inverso = self.nome_inverso

        chave_origem = self.chave_origem

        chave_destino = self.chave_destino

        composto = self.composto

        cardinalidade_min: int | None | Unset
        if isinstance(self.cardinalidade_min, Unset):
            cardinalidade_min = UNSET
        else:
            cardinalidade_min = self.cardinalidade_min

        cardinalidade_max: int | None | Unset
        if isinstance(self.cardinalidade_max, Unset):
            cardinalidade_max = UNSET
        else:
            cardinalidade_max = self.cardinalidade_max

        limite_relacionados = self.limite_relacionados

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "origem_item_id": origem_item_id,
                "destino_item_id": destino_item_id,
                "cardinalidade": cardinalidade,
                "nome_direto": nome_direto,
                "nome_inverso": nome_inverso,
            }
        )
        if chave_origem is not UNSET:
            field_dict["chave_origem"] = chave_origem
        if chave_destino is not UNSET:
            field_dict["chave_destino"] = chave_destino
        if composto is not UNSET:
            field_dict["composto"] = composto
        if cardinalidade_min is not UNSET:
            field_dict["cardinalidade_min"] = cardinalidade_min
        if cardinalidade_max is not UNSET:
            field_dict["cardinalidade_max"] = cardinalidade_max
        if limite_relacionados is not UNSET:
            field_dict["limite_relacionados"] = limite_relacionados

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        origem_item_id = d.pop("origem_item_id")

        destino_item_id = d.pop("destino_item_id")

        cardinalidade = d.pop("cardinalidade")

        nome_direto = d.pop("nome_direto")

        nome_inverso = d.pop("nome_inverso")

        chave_origem = d.pop("chave_origem", UNSET)

        chave_destino = d.pop("chave_destino", UNSET)

        composto = d.pop("composto", UNSET)

        def _parse_cardinalidade_min(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cardinalidade_min = _parse_cardinalidade_min(d.pop("cardinalidade_min", UNSET))

        def _parse_cardinalidade_max(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cardinalidade_max = _parse_cardinalidade_max(d.pop("cardinalidade_max", UNSET))

        limite_relacionados = d.pop("limite_relacionados", UNSET)

        relacionamento_entrada = cls(
            origem_item_id=origem_item_id,
            destino_item_id=destino_item_id,
            cardinalidade=cardinalidade,
            nome_direto=nome_direto,
            nome_inverso=nome_inverso,
            chave_origem=chave_origem,
            chave_destino=chave_destino,
            composto=composto,
            cardinalidade_min=cardinalidade_min,
            cardinalidade_max=cardinalidade_max,
            limite_relacionados=limite_relacionados,
        )

        return relacionamento_entrada
