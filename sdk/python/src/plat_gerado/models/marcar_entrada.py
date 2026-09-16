from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="MarcarEntrada")


@_attrs_define
class MarcarEntrada:
    """
    Attributes:
        ids (list[str] | None | Unset):
        todas (bool | Unset):  Default: False.
    """

    ids: list[str] | None | Unset = UNSET
    todas: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        ids: list[str] | None | Unset
        if isinstance(self.ids, Unset):
            ids = UNSET
        elif isinstance(self.ids, list):
            ids = self.ids

        else:
            ids = self.ids

        todas = self.todas

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if ids is not UNSET:
            field_dict["ids"] = ids
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

        todas = d.pop("todas", UNSET)

        marcar_entrada = cls(
            ids=ids,
            todas=todas,
        )

        return marcar_entrada
