from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RelacionamentoSaida")


@_attrs_define
class RelacionamentoSaida:
    """
    Attributes:
        id (str):
        origem_item_id (str):
        destino_item_id (str):
        cardinalidade (str):
        chave_origem (str):
        chave_destino (str):
        composto (bool):
        nome_direto (str):
        nome_inverso (str):
        cardinalidade_min (int | None):
        cardinalidade_max (int | None):
        limite_relacionados (int):
        criado_em (None | str | Unset):
    """

    id: str
    origem_item_id: str
    destino_item_id: str
    cardinalidade: str
    chave_origem: str
    chave_destino: str
    composto: bool
    nome_direto: str
    nome_inverso: str
    cardinalidade_min: int | None
    cardinalidade_max: int | None
    limite_relacionados: int
    criado_em: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        origem_item_id = self.origem_item_id

        destino_item_id = self.destino_item_id

        cardinalidade = self.cardinalidade

        chave_origem = self.chave_origem

        chave_destino = self.chave_destino

        composto = self.composto

        nome_direto = self.nome_direto

        nome_inverso = self.nome_inverso

        cardinalidade_min: int | None
        cardinalidade_min = self.cardinalidade_min

        cardinalidade_max: int | None
        cardinalidade_max = self.cardinalidade_max

        limite_relacionados = self.limite_relacionados

        criado_em: None | str | Unset
        if isinstance(self.criado_em, Unset):
            criado_em = UNSET
        else:
            criado_em = self.criado_em

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "origem_item_id": origem_item_id,
                "destino_item_id": destino_item_id,
                "cardinalidade": cardinalidade,
                "chave_origem": chave_origem,
                "chave_destino": chave_destino,
                "composto": composto,
                "nome_direto": nome_direto,
                "nome_inverso": nome_inverso,
                "cardinalidade_min": cardinalidade_min,
                "cardinalidade_max": cardinalidade_max,
                "limite_relacionados": limite_relacionados,
            }
        )
        if criado_em is not UNSET:
            field_dict["criado_em"] = criado_em

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        origem_item_id = d.pop("origem_item_id")

        destino_item_id = d.pop("destino_item_id")

        cardinalidade = d.pop("cardinalidade")

        chave_origem = d.pop("chave_origem")

        chave_destino = d.pop("chave_destino")

        composto = d.pop("composto")

        nome_direto = d.pop("nome_direto")

        nome_inverso = d.pop("nome_inverso")

        def _parse_cardinalidade_min(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cardinalidade_min = _parse_cardinalidade_min(d.pop("cardinalidade_min"))

        def _parse_cardinalidade_max(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        cardinalidade_max = _parse_cardinalidade_max(d.pop("cardinalidade_max"))

        limite_relacionados = d.pop("limite_relacionados")

        def _parse_criado_em(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        criado_em = _parse_criado_em(d.pop("criado_em", UNSET))

        relacionamento_saida = cls(
            id=id,
            origem_item_id=origem_item_id,
            destino_item_id=destino_item_id,
            cardinalidade=cardinalidade,
            chave_origem=chave_origem,
            chave_destino=chave_destino,
            composto=composto,
            nome_direto=nome_direto,
            nome_inverso=nome_inverso,
            cardinalidade_min=cardinalidade_min,
            cardinalidade_max=cardinalidade_max,
            limite_relacionados=limite_relacionados,
            criado_em=criado_em,
        )

        relacionamento_saida.additional_properties = d
        return relacionamento_saida

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
