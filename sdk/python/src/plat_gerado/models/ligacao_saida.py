from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LigacaoSaida")


@_attrs_define
class LigacaoSaida:
    """
    Attributes:
        id (str):
        item_id (str):
        campo (str):
        dominio_id (str):
        dominio_nome (str):
        subtipo_codigo (int | None | Unset):
    """

    id: str
    item_id: str
    campo: str
    dominio_id: str
    dominio_nome: str
    subtipo_codigo: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        item_id = self.item_id

        campo = self.campo

        dominio_id = self.dominio_id

        dominio_nome = self.dominio_nome

        subtipo_codigo: int | None | Unset
        if isinstance(self.subtipo_codigo, Unset):
            subtipo_codigo = UNSET
        else:
            subtipo_codigo = self.subtipo_codigo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "item_id": item_id,
                "campo": campo,
                "dominio_id": dominio_id,
                "dominio_nome": dominio_nome,
            }
        )
        if subtipo_codigo is not UNSET:
            field_dict["subtipo_codigo"] = subtipo_codigo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        item_id = d.pop("item_id")

        campo = d.pop("campo")

        dominio_id = d.pop("dominio_id")

        dominio_nome = d.pop("dominio_nome")

        def _parse_subtipo_codigo(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        subtipo_codigo = _parse_subtipo_codigo(d.pop("subtipo_codigo", UNSET))

        ligacao_saida = cls(
            id=id,
            item_id=item_id,
            campo=campo,
            dominio_id=dominio_id,
            dominio_nome=dominio_nome,
            subtipo_codigo=subtipo_codigo,
        )

        ligacao_saida.additional_properties = d
        return ligacao_saida

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
