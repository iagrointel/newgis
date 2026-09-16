from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SiteEntrada")


@_attrs_define
class SiteEntrada:
    """
    Attributes:
        indexavel (bool | Unset):  Default: False.
        versao (int | None | Unset):
    """

    indexavel: bool | Unset = False
    versao: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        indexavel = self.indexavel

        versao: int | None | Unset
        if isinstance(self.versao, Unset):
            versao = UNSET
        else:
            versao = self.versao

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if indexavel is not UNSET:
            field_dict["indexavel"] = indexavel
        if versao is not UNSET:
            field_dict["versao"] = versao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        indexavel = d.pop("indexavel", UNSET)

        def _parse_versao(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        versao = _parse_versao(d.pop("versao", UNSET))

        site_entrada = cls(
            indexavel=indexavel,
            versao=versao,
        )

        return site_entrada
