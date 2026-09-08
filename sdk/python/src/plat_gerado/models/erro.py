from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Erro")


@_attrs_define
class Erro:
    """
    Attributes:
        erro (str):
        mensagem (str):
        detalhe (Any | None | Unset):
        req_id (None | str | Unset):
    """

    erro: str
    mensagem: str
    detalhe: Any | None | Unset = UNSET
    req_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        erro = self.erro

        mensagem = self.mensagem

        detalhe: Any | None | Unset
        if isinstance(self.detalhe, Unset):
            detalhe = UNSET
        else:
            detalhe = self.detalhe

        req_id: None | str | Unset
        if isinstance(self.req_id, Unset):
            req_id = UNSET
        else:
            req_id = self.req_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "erro": erro,
                "mensagem": mensagem,
            }
        )
        if detalhe is not UNSET:
            field_dict["detalhe"] = detalhe
        if req_id is not UNSET:
            field_dict["req_id"] = req_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        erro = d.pop("erro")

        mensagem = d.pop("mensagem")

        def _parse_detalhe(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        detalhe = _parse_detalhe(d.pop("detalhe", UNSET))

        def _parse_req_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        req_id = _parse_req_id(d.pop("req_id", UNSET))

        erro = cls(
            erro=erro,
            mensagem=mensagem,
            detalhe=detalhe,
            req_id=req_id,
        )

        erro.additional_properties = d
        return erro

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
