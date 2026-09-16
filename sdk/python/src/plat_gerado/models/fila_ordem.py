from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="FilaOrdem")


@_attrs_define
class FilaOrdem:
    """
    Attributes:
        alvo_ids (list[str]):
    """

    alvo_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        alvo_ids = self.alvo_ids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "alvo_ids": alvo_ids,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        alvo_ids = cast(list[str], d.pop("alvo_ids"))

        fila_ordem = cls(
            alvo_ids=alvo_ids,
        )

        return fila_ordem
