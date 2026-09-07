from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SMTPTestarEntrada")


@_attrs_define
class SMTPTestarEntrada:
    """
    Attributes:
        destinatario (None | str | Unset):
    """

    destinatario: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        destinatario: None | str | Unset
        if isinstance(self.destinatario, Unset):
            destinatario = UNSET
        else:
            destinatario = self.destinatario

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if destinatario is not UNSET:
            field_dict["destinatario"] = destinatario

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_destinatario(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        destinatario = _parse_destinatario(d.pop("destinatario", UNSET))

        smtp_testar_entrada = cls(
            destinatario=destinatario,
        )

        return smtp_testar_entrada
