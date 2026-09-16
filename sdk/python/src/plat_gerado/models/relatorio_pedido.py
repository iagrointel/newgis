from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RelatorioPedido")


@_attrs_define
class RelatorioPedido:
    """
    Attributes:
        tipo (str):
        desde (None | str | Unset):
        ate (None | str | Unset):
        email (bool | Unset):  Default: False.
    """

    tipo: str
    desde: None | str | Unset = UNSET
    ate: None | str | Unset = UNSET
    email: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        desde: None | str | Unset
        if isinstance(self.desde, Unset):
            desde = UNSET
        else:
            desde = self.desde

        ate: None | str | Unset
        if isinstance(self.ate, Unset):
            ate = UNSET
        else:
            ate = self.ate

        email = self.email

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
            }
        )
        if desde is not UNSET:
            field_dict["desde"] = desde
        if ate is not UNSET:
            field_dict["ate"] = ate
        if email is not UNSET:
            field_dict["email"] = email

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo")

        def _parse_desde(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        desde = _parse_desde(d.pop("desde", UNSET))

        def _parse_ate(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ate = _parse_ate(d.pop("ate", UNSET))

        email = d.pop("email", UNSET)

        relatorio_pedido = cls(
            tipo=tipo,
            desde=desde,
            ate=ate,
            email=email,
        )

        return relatorio_pedido
