from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LigacaoEntradaDominios")


@_attrs_define
class LigacaoEntradaDominios:
    """
    Attributes:
        campo (str):
        dominio_id (str):
        subtipo_codigo (int | None | Unset):
    """

    campo: str
    dominio_id: str
    subtipo_codigo: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        campo = self.campo

        dominio_id = self.dominio_id

        subtipo_codigo: int | None | Unset
        if isinstance(self.subtipo_codigo, Unset):
            subtipo_codigo = UNSET
        else:
            subtipo_codigo = self.subtipo_codigo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "campo": campo,
                "dominio_id": dominio_id,
            }
        )
        if subtipo_codigo is not UNSET:
            field_dict["subtipo_codigo"] = subtipo_codigo

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        campo = d.pop("campo")

        dominio_id = d.pop("dominio_id")

        def _parse_subtipo_codigo(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        subtipo_codigo = _parse_subtipo_codigo(d.pop("subtipo_codigo", UNSET))

        ligacao_entrada_dominios = cls(
            campo=campo,
            dominio_id=dominio_id,
            subtipo_codigo=subtipo_codigo,
        )

        return ligacao_entrada_dominios
