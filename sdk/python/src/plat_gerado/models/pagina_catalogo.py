from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PaginaCatalogo")


@_attrs_define
class PaginaCatalogo:
    """
    Attributes:
        total (int):
        itens (list[Any]):
        proximo_cursor (None | str | Unset):
        aproximado (bool | None | Unset):
    """

    total: int
    itens: list[Any]
    proximo_cursor: None | str | Unset = UNSET
    aproximado: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        itens = self.itens

        proximo_cursor: None | str | Unset
        if isinstance(self.proximo_cursor, Unset):
            proximo_cursor = UNSET
        else:
            proximo_cursor = self.proximo_cursor

        aproximado: bool | None | Unset
        if isinstance(self.aproximado, Unset):
            aproximado = UNSET
        else:
            aproximado = self.aproximado

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "itens": itens,
            }
        )
        if proximo_cursor is not UNSET:
            field_dict["proximo_cursor"] = proximo_cursor
        if aproximado is not UNSET:
            field_dict["aproximado"] = aproximado

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total = d.pop("total")

        itens = cast(list[Any], d.pop("itens"))

        def _parse_proximo_cursor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        proximo_cursor = _parse_proximo_cursor(d.pop("proximo_cursor", UNSET))

        def _parse_aproximado(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        aproximado = _parse_aproximado(d.pop("aproximado", UNSET))

        pagina_catalogo = cls(
            total=total,
            itens=itens,
            proximo_cursor=proximo_cursor,
            aproximado=aproximado,
        )

        pagina_catalogo.additional_properties = d
        return pagina_catalogo

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
