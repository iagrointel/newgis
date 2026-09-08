from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoteEntradaAuth")


@_attrs_define
class LoteEntradaAuth:
    """
    Attributes:
        ids (list[int]):
        acao (str):
        perfil (None | str | Unset):
        papel_id (int | None | Unset):
    """

    ids: list[int]
    acao: str
    perfil: None | str | Unset = UNSET
    papel_id: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        ids = self.ids

        acao = self.acao

        perfil: None | str | Unset
        if isinstance(self.perfil, Unset):
            perfil = UNSET
        else:
            perfil = self.perfil

        papel_id: int | None | Unset
        if isinstance(self.papel_id, Unset):
            papel_id = UNSET
        else:
            papel_id = self.papel_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ids": ids,
                "acao": acao,
            }
        )
        if perfil is not UNSET:
            field_dict["perfil"] = perfil
        if papel_id is not UNSET:
            field_dict["papel_id"] = papel_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ids = cast(list[int], d.pop("ids"))

        acao = d.pop("acao")

        def _parse_perfil(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        perfil = _parse_perfil(d.pop("perfil", UNSET))

        def _parse_papel_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        papel_id = _parse_papel_id(d.pop("papel_id", UNSET))

        lote_entrada_auth = cls(
            ids=ids,
            acao=acao,
            perfil=perfil,
            papel_id=papel_id,
        )

        return lote_entrada_auth
