from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.login_provedor_entrada_provisionamento_type_0 import LoginProvedorEntradaProvisionamentoType0


T = TypeVar("T", bound="LoginProvedorEntrada")


@_attrs_define
class LoginProvedorEntrada:
    """
    Attributes:
        habilitado (bool | None | Unset):
        rotulo (None | str | Unset):
        ordem (int | None | Unset):
        provisionamento (LoginProvedorEntradaProvisionamentoType0 | None | Unset):
    """

    habilitado: bool | None | Unset = UNSET
    rotulo: None | str | Unset = UNSET
    ordem: int | None | Unset = UNSET
    provisionamento: LoginProvedorEntradaProvisionamentoType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.login_provedor_entrada_provisionamento_type_0 import (
            LoginProvedorEntradaProvisionamentoType0,  # noqa: PLC0415
        )

        habilitado: bool | None | Unset
        if isinstance(self.habilitado, Unset):
            habilitado = UNSET
        else:
            habilitado = self.habilitado

        rotulo: None | str | Unset
        if isinstance(self.rotulo, Unset):
            rotulo = UNSET
        else:
            rotulo = self.rotulo

        ordem: int | None | Unset
        if isinstance(self.ordem, Unset):
            ordem = UNSET
        else:
            ordem = self.ordem

        provisionamento: dict[str, Any] | None | Unset
        if isinstance(self.provisionamento, Unset):
            provisionamento = UNSET
        elif isinstance(self.provisionamento, LoginProvedorEntradaProvisionamentoType0):
            provisionamento = self.provisionamento.to_dict()
        else:
            provisionamento = self.provisionamento

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if habilitado is not UNSET:
            field_dict["habilitado"] = habilitado
        if rotulo is not UNSET:
            field_dict["rotulo"] = rotulo
        if ordem is not UNSET:
            field_dict["ordem"] = ordem
        if provisionamento is not UNSET:
            field_dict["provisionamento"] = provisionamento

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.login_provedor_entrada_provisionamento_type_0 import (
            LoginProvedorEntradaProvisionamentoType0,  # noqa: PLC0415
        )

        d = dict(src_dict)

        def _parse_habilitado(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        habilitado = _parse_habilitado(d.pop("habilitado", UNSET))

        def _parse_rotulo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rotulo = _parse_rotulo(d.pop("rotulo", UNSET))

        def _parse_ordem(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ordem = _parse_ordem(d.pop("ordem", UNSET))

        def _parse_provisionamento(data: object) -> LoginProvedorEntradaProvisionamentoType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                provisionamento_type_0 = LoginProvedorEntradaProvisionamentoType0.from_dict(data)

                return provisionamento_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LoginProvedorEntradaProvisionamentoType0 | None | Unset, data)

        provisionamento = _parse_provisionamento(d.pop("provisionamento", UNSET))

        login_provedor_entrada = cls(
            habilitado=habilitado,
            rotulo=rotulo,
            ordem=ordem,
            provisionamento=provisionamento,
        )

        return login_provedor_entrada
