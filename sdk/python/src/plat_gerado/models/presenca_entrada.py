from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PresencaEntrada")


@_attrs_define
class PresencaEntrada:
    """
    Attributes:
        sessao (str):
        no (None | str | Unset):
        sair (bool | Unset):  Default: False.
    """

    sessao: str
    no: None | str | Unset = UNSET
    sair: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        sessao = self.sessao

        no: None | str | Unset
        if isinstance(self.no, Unset):
            no = UNSET
        else:
            no = self.no

        sair = self.sair

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "sessao": sessao,
            }
        )
        if no is not UNSET:
            field_dict["no"] = no
        if sair is not UNSET:
            field_dict["sair"] = sair

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        sessao = d.pop("sessao")

        def _parse_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        no = _parse_no(d.pop("no", UNSET))

        sair = d.pop("sair", UNSET)

        presenca_entrada = cls(
            sessao=sessao,
            no=no,
            sair=sair,
        )

        return presenca_entrada
