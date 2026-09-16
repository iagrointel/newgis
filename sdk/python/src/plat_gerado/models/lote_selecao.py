from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoteSelecao")


@_attrs_define
class LoteSelecao:
    """Exatamente uma das três formas: `ids` (globalids), `onde` (expressão booleana da linguagem L2-10-c sobre
    os campos da camada) ou `todas`.

        Attributes:
            ids (list[str] | None | Unset):
            onde (None | str | Unset):
            todas (bool | Unset):  Default: False.
    """

    ids: list[str] | None | Unset = UNSET
    onde: None | str | Unset = UNSET
    todas: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        ids: list[str] | None | Unset
        if isinstance(self.ids, Unset):
            ids = UNSET
        elif isinstance(self.ids, list):
            ids = self.ids

        else:
            ids = self.ids

        onde: None | str | Unset
        if isinstance(self.onde, Unset):
            onde = UNSET
        else:
            onde = self.onde

        todas = self.todas

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if ids is not UNSET:
            field_dict["ids"] = ids
        if onde is not UNSET:
            field_dict["onde"] = onde
        if todas is not UNSET:
            field_dict["todas"] = todas

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                ids_type_0 = cast(list[str], data)

                return ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        ids = _parse_ids(d.pop("ids", UNSET))

        def _parse_onde(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        onde = _parse_onde(d.pop("onde", UNSET))

        todas = d.pop("todas", UNSET)

        lote_selecao = cls(
            ids=ids,
            onde=onde,
            todas=todas,
        )

        return lote_selecao
