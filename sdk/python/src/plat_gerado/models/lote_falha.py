from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoteFalha")


@_attrs_define
class LoteFalha:
    """
    Attributes:
        erro (str):
        mensagem (str):
        id (None | str | Unset):
        detalhe (Any | Unset):
    """

    erro: str
    mensagem: str
    id: None | str | Unset = UNSET
    detalhe: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        erro = self.erro

        mensagem = self.mensagem

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        detalhe = self.detalhe

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "erro": erro,
                "mensagem": mensagem,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if detalhe is not UNSET:
            field_dict["detalhe"] = detalhe

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        erro = d.pop("erro")

        mensagem = d.pop("mensagem")

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        detalhe = d.pop("detalhe", UNSET)

        lote_falha = cls(
            erro=erro,
            mensagem=mensagem,
            id=id,
            detalhe=detalhe,
        )

        lote_falha.additional_properties = d
        return lote_falha

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
