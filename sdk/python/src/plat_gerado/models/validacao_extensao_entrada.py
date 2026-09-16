from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validacao_extensao_entrada_extensao_type_0 import ValidacaoExtensaoEntradaExtensaoType0


T = TypeVar("T", bound="ValidacaoExtensaoEntrada")


@_attrs_define
class ValidacaoExtensaoEntrada:
    """
    Attributes:
        extensao (None | Unset | ValidacaoExtensaoEntradaExtensaoType0):
    """

    extensao: None | Unset | ValidacaoExtensaoEntradaExtensaoType0 = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.validacao_extensao_entrada_extensao_type_0 import (
            ValidacaoExtensaoEntradaExtensaoType0,  # noqa: PLC0415
        )

        extensao: dict[str, Any] | None | Unset
        if isinstance(self.extensao, Unset):
            extensao = UNSET
        elif isinstance(self.extensao, ValidacaoExtensaoEntradaExtensaoType0):
            extensao = self.extensao.to_dict()
        else:
            extensao = self.extensao

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if extensao is not UNSET:
            field_dict["extensao"] = extensao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validacao_extensao_entrada_extensao_type_0 import (
            ValidacaoExtensaoEntradaExtensaoType0,  # noqa: PLC0415
        )

        d = dict(src_dict)

        def _parse_extensao(data: object) -> None | Unset | ValidacaoExtensaoEntradaExtensaoType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extensao_type_0 = ValidacaoExtensaoEntradaExtensaoType0.from_dict(data)

                return extensao_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | ValidacaoExtensaoEntradaExtensaoType0, data)

        extensao = _parse_extensao(d.pop("extensao", UNSET))

        validacao_extensao_entrada = cls(
            extensao=extensao,
        )

        return validacao_extensao_entrada
